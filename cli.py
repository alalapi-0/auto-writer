"""AutoWriter 半自动导出与剪贴板助手 CLI。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Tuple

from autowriter_text.pipeline.postprocess import (
    ArticleRow,
    collect_articles_for_date,
    is_similar_recent,
)

from automation import WeChatAutomator, ZhihuAutomator, connect_chrome_cdp
from automation.utils import human_sleep

from exporter.common import ensure_dir, export_index_csv_json
from exporter.packer import bundle_all, zip_dir
from exporter.wechat_exporter import export_for_wechat
from exporter.zhihu_exporter import export_for_zhihu


def _parse_date(value: str | None) -> str:
    """解析日期字符串，默认返回当天日期。"""

    if value:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    # 没有传入时按 UTC+0 生成日期字符串，确保跨时区稳定。
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _require_articles(date_str: str) -> list[ArticleRow]:
    """从数据库获取文章，若为空则退出。"""

    articles = collect_articles_for_date(date_str)
    if not articles:
        raise SystemExit(f"{date_str} 无可导出的文章，请确认生成流程是否完成。")
    return articles


def _select_articles(date_str: str, limit: int) -> list[ArticleRow]:
    """获取指定日期的文章并限制篇幅。"""

    return _require_articles(date_str)[: max(1, limit)]


def _export_wechat(articles: list[ArticleRow], date_str: str, base_dir: Path) -> Tuple[Path, Path]:
    """执行公众号导出并返回日期目录与 zip 路径。"""

    date_dir = ensure_dir(base_dir / date_str)
    rows = export_for_wechat(articles, date_dir)
    export_index_csv_json(date_dir, rows)
    zip_path = date_dir.parent / f"wechat_{date_str}.zip"
    zip_dir(date_dir, zip_path)
    print(f"[wechat] 导出完成：{date_dir} -> {zip_path}")
    return Path(date_dir), zip_path


def _export_zhihu(articles: list[ArticleRow], date_str: str, base_dir: Path) -> Tuple[Path, Path]:
    """执行知乎导出并返回日期目录与 zip 路径。"""

    date_dir = ensure_dir(base_dir / date_str)
    rows = export_for_zhihu(articles, date_dir)
    export_index_csv_json(date_dir, rows)
    zip_path = date_dir.parent / f"zhihu_{date_str}.zip"
    zip_dir(date_dir, zip_path)
    print(f"[zhihu] 导出完成：{date_dir} -> {zip_path}")
    return Path(date_dir), zip_path


def cmd_export(args: argparse.Namespace) -> None:
    """处理 export 子命令。"""

    date_str = _parse_date(args.date)
    articles = _require_articles(date_str)
    if args.platform == "wechat":
        _export_wechat(articles, date_str, Path(args.out or "exports/wechat"))
    elif args.platform == "zhihu":
        _export_zhihu(articles, date_str, Path(args.out or "exports/zhihu"))
    else:
        wechat_dir, _ = _export_wechat(articles, date_str, Path("exports/wechat"))
        zhihu_dir, _ = _export_zhihu(articles, date_str, Path("exports/zhihu"))
        bundle_path = Path("exports") / f"bundle_all_{date_str}.zip"
        bundle_all(wechat_dir, zhihu_dir, bundle_path)
        print(f"[bundle] 已生成组合压缩包：{bundle_path}")


def _iter_copy_targets(platform: str, article_dir: Path) -> Iterable[tuple[str, Path]]:
    """返回剪贴板复制顺序。"""

    if platform == "wechat":
        return (
            ("标题", article_dir / "title.txt"),
            ("摘要", article_dir / "digest.txt"),
            ("正文 HTML", article_dir / "article.html"),
        )
    return (
        ("标题", article_dir / "title.txt"),
        ("正文 Markdown", article_dir / "article.md"),
    )


def cmd_copy(args: argparse.Namespace) -> None:
    """处理 copy 子命令，交互式写入剪贴板。"""

    try:
        import pyperclip
        from pyperclip import PyperclipException
    except ImportError as exc:  # pragma: no cover - 依赖缺失时提示用户
        raise SystemExit("未安装 pyperclip，请先执行 pip install pyperclip") from exc

    # 提前检测剪贴板是否可用，避免流程中途失败。
    try:
        pyperclip.copy("")
    except PyperclipException as exc:  # pragma: no cover - 系统剪贴板不可用
        raise SystemExit(f"无法访问系统剪贴板：{exc}") from exc

    date_str = _parse_date(args.date)
    base_dir = Path("exports/wechat" if args.platform == "wechat" else "exports/zhihu")
    date_dir = base_dir / date_str
    if not date_dir.exists():
        raise SystemExit(f"未找到导出目录：{date_dir}，请先执行 export {args.platform}")

    article_dirs = sorted([p for p in date_dir.iterdir() if p.is_dir()])
    if not article_dirs:
        raise SystemExit(f"目录 {date_dir} 下没有文章，请检查导出结果。")

    index = max(1, args.index)
    try:
        target_dir = article_dirs[index - 1]
    except IndexError as exc:
        raise SystemExit(f"索引 {index} 超出范围，共有 {len(article_dirs)} 篇。") from exc

    targets = list(_iter_copy_targets(args.platform, target_dir))
    print(f"开始复制 {target_dir.name}，共 {len(targets)} 步。")
    for label, file_path in targets:
        if not file_path.exists():
            raise SystemExit(f"缺少必要文件：{file_path}")
        content = file_path.read_text(encoding="utf-8")
        pyperclip.copy(content)
        input(f"已复制{label} → 请粘贴到目标页面后按回车继续…")
    print("复制流程完成，可开始下一个字段或文章。")


def cmd_auto(args: argparse.Namespace) -> None:
    """处理 auto 子命令，使用本机浏览器自动创建草稿。"""

    date_str = _parse_date(args.date)  # 解析目标日期。
    limit = getattr(args, "limit", 5) or 5  # 控制单次送稿的篇数。
    articles = _select_articles(date_str, limit)  # 读取当日素材。
    dry_run = bool(getattr(args, "dry_run", False))  # 是否仅演练不保存。
    max_retries = max(1, int(getattr(args, "max_retries", 3)))  # 单篇最大重试次数。
    min_interval = float(getattr(args, "min_interval", 6.0))  # 跨篇节流下限。
    max_interval = float(getattr(args, "max_interval", 12.0))  # 跨篇节流上限。
    if max_interval < min_interval:
        max_interval = min_interval  # 保证区间有效。
    try:
        context = connect_chrome_cdp(getattr(args, "cdp", "http://127.0.0.1:9222"))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - Playwright 环境相关
        raise SystemExit(f"连接 Chrome 失败：{exc}") from exc
    playwright = getattr(context, "_automation_playwright", None)

    platforms: tuple[str, ...]
    if args.platform == "wechat":
        platforms = ("wechat",)
    elif args.platform == "zhihu":
        platforms = ("zhihu",)
    else:
        platforms = ("wechat", "zhihu")

    wechat = WeChatAutomator(context) if "wechat" in platforms else None  # 初始化公众号自动化实例。
    zhihu = ZhihuAutomator(context) if "zhihu" in platforms else None  # 初始化知乎自动化实例。
    results: list[dict[str, object]] = []  # 累积所有平台的执行结果。

    try:
        for idx, article in enumerate(articles, start=1):
            similar, match_title = is_similar_recent(article.title)  # 去重检测。
            if similar:
                reason = f"similar to <{match_title}>"
                for platform in platforms:
                    entry = {
                        "ok": False,
                        "platform": platform,
                        "title": article.title,
                        "reason": reason,
                        "screenshot": "",
                        "skipped": True,
                    }
                    results.append(entry)
                    print(f"[{platform}] {article.title} ... SKIP ({reason})")
                continue

            for platform in platforms:
                if platform == "wechat" and wechat is not None:
                    result = wechat.create_draft(
                        article,
                        screenshot_prefix=f"wechat_{date_str}_{idx:02d}",
                        dry_run=dry_run,
                        max_retries=max_retries,
                    )
                elif platform == "zhihu" and zhihu is not None:
                    result = zhihu.create_draft(
                        article,
                        dry_run=dry_run,
                        max_retries=max_retries,
                    )
                else:  # pragma: no cover - 理论上不会触发
                    continue
                result.setdefault("skipped", False)  # 统一附带 skipped 字段，便于统计。
                results.append(result)
                status = "OK" if result.get("ok") else ("SKIP" if result.get("skipped") else "FAIL")
                reason = result.get("reason", "")
                screenshot = result.get("screenshot") or ""
                shot_text = f" [shot: {screenshot}]" if screenshot else ""
                print(f"[{platform}] {article.title} ... {status} ({reason}){shot_text}")  # 逐篇打印结果。
            if idx < len(articles):
                human_sleep(min_interval, max_interval)  # 跨篇随机等待，模拟人工节奏。
    finally:
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # pragma: no cover - Playwright 清理失败时忽略
                pass

    success_count = sum(1 for item in results if item.get("ok"))  # 成功篇目数。
    skipped_count = sum(1 for item in results if item.get("skipped"))  # 去重或手动跳过数。
    failed_count = len(results) - success_count - skipped_count  # 其余视为失败。
    print(f"完成：成功 {success_count} / 跳过 {skipped_count} / 失败 {failed_count}")

    log_dir = Path("automation_logs") / date_str  # 每日汇总目录。
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_path = log_dir / "summary.json"
    payload = {
        "date": date_str,
        "dry_run": dry_run,
        "max_retries": max_retries,
        "interval": {"min": min_interval, "max": max_interval},
        "results": results,
        "counters": {
            "success": success_count,
            "skipped": skipped_count,
            "failed": failed_count,
        },
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"运行详情已保存至 {summary_path}")  # 输出汇总文件路径。


def build_parser() -> argparse.ArgumentParser:
    """构建顶级参数解析器。"""

    parser = argparse.ArgumentParser(description="AutoWriter 半自动导出 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="导出文章素材包")
    export_sub = export_parser.add_subparsers(dest="platform", required=True)

    wechat_parser = export_sub.add_parser("wechat", help="导出微信公众号草稿")
    wechat_parser.add_argument("--date", help="目标日期，默认当天")
    wechat_parser.add_argument("--out", help="输出根目录，默认 exports/wechat")
    wechat_parser.set_defaults(func=cmd_export)

    zhihu_parser = export_sub.add_parser("zhihu", help="导出知乎文章")
    zhihu_parser.add_argument("--date", help="目标日期，默认当天")
    zhihu_parser.add_argument("--out", help="输出根目录，默认 exports/zhihu")
    zhihu_parser.set_defaults(func=cmd_export)

    all_parser = export_sub.add_parser("all", help="同时导出两个平台")
    all_parser.add_argument("--date", help="目标日期，默认当天")
    all_parser.set_defaults(func=cmd_export)

    copy_parser = subparsers.add_parser("copy", help="逐段复制到剪贴板")
    copy_sub = copy_parser.add_subparsers(dest="platform", required=True)

    copy_wechat = copy_sub.add_parser("wechat", help="复制公众号标题/摘要/正文")
    copy_wechat.add_argument("--date", help="目标日期，默认当天")
    copy_wechat.add_argument("--index", type=int, default=1, help="文章序号（从 1 开始）")
    copy_wechat.set_defaults(func=cmd_copy)

    copy_zhihu = copy_sub.add_parser("zhihu", help="复制知乎标题与正文")
    copy_zhihu.add_argument("--date", help="目标日期，默认当天")
    copy_zhihu.add_argument("--index", type=int, default=1, help="文章序号（从 1 开始）")
    copy_zhihu.set_defaults(func=cmd_copy)

    auto_parser = subparsers.add_parser("auto", help="自动送草稿到目标平台")
    auto_sub = auto_parser.add_subparsers(dest="platform", required=True)

    auto_wechat = auto_sub.add_parser("wechat", help="送公众号草稿")
    auto_wechat.add_argument("--date", help="目标日期，默认当天")
    auto_wechat.add_argument("--limit", type=int, default=5, help="送入草稿的篇数")
    auto_wechat.add_argument("--cdp", default="http://127.0.0.1:9222", help="Chrome CDP 地址")
    auto_wechat.add_argument("--dry-run", action="store_true", help="仅演练到定位编辑器，不提交保存")
    auto_wechat.add_argument("--max-retries", type=int, default=3, help="同一篇草稿失败后的最大重试次数")
    auto_wechat.add_argument("--min-interval", type=float, default=6.0, help="跨篇等待的最小秒数")
    auto_wechat.add_argument("--max-interval", type=float, default=12.0, help="跨篇等待的最大秒数")
    auto_wechat.set_defaults(func=cmd_auto)

    auto_zhihu = auto_sub.add_parser("zhihu", help="送知乎草稿")
    auto_zhihu.add_argument("--date", help="目标日期，默认当天")
    auto_zhihu.add_argument("--limit", type=int, default=5, help="送入草稿的篇数")
    auto_zhihu.add_argument("--cdp", default="http://127.0.0.1:9222", help="Chrome CDP 地址")
    auto_zhihu.add_argument("--dry-run", action="store_true", help="仅演练到定位编辑器，不提交保存")
    auto_zhihu.add_argument("--max-retries", type=int, default=3, help="同一篇草稿失败后的最大重试次数")
    auto_zhihu.add_argument("--min-interval", type=float, default=6.0, help="跨篇等待的最小秒数")
    auto_zhihu.add_argument("--max-interval", type=float, default=12.0, help="跨篇等待的最大秒数")
    auto_zhihu.set_defaults(func=cmd_auto)

    auto_all = auto_sub.add_parser("all", help="两个平台同时送草稿")
    auto_all.add_argument("--date", help="目标日期，默认当天")
    auto_all.add_argument("--limit", type=int, default=5, help="送入草稿的篇数")
    auto_all.add_argument(
        "--cdp", default="http://127.0.0.1:9222", help="Chrome CDP 地址（两个平台共用）"
    )
    auto_all.add_argument("--dry-run", action="store_true", help="仅演练到定位编辑器，不提交保存")
    auto_all.add_argument("--max-retries", type=int, default=3, help="同一篇草稿失败后的最大重试次数")
    auto_all.add_argument("--min-interval", type=float, default=6.0, help="跨篇等待的最小秒数")
    auto_all.add_argument("--max-interval", type=float, default=12.0, help="跨篇等待的最大秒数")
    auto_all.set_defaults(func=cmd_auto)

    return parser


def main() -> None:
    """命令行入口。"""

    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    main()
