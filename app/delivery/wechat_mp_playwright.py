"""使用 Playwright 将草稿导入微信公众号后台。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法

import json  # 解析 meta 信息
from pathlib import Path  # 操作本地文件
from typing import Dict, Optional  # 类型注解

import structlog  # 结构化日志
from playwright.sync_api import Error as PlaywrightError  # Playwright 异常

from app.automation import wechat_mp_bot  # 导入公众号 Bot
from app.automation.pw_helper import (  # 辅助 Playwright 函数
    launch_browser,  # 启动浏览器
    shoot,  # 截图
    stop_browser,  # 关闭浏览器
)
from app.delivery.types import DeliveryResult  # 统一返回类型

LOGGER = structlog.get_logger(__name__)  # 初始化日志器


def _load_material(out_dir: Path) -> Dict[str, object]:  # 从 outbox 读取草稿材料
    """读取 Markdown、HTML 与 meta 文件，返回统一字典。"""  # 中文说明

    if not out_dir.exists():  # 路径不存在
        raise FileNotFoundError(f"公众号草稿目录不存在: {out_dir}")  # 抛出异常
    md_path = out_dir / "draft.md"  # Markdown 路径
    html_path = out_dir / "draft.html"  # HTML 路径
    meta_path = out_dir / "meta.json"  # meta 路径
    plain_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""  # 读取 Markdown
    md_html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""  # 读取 HTML
    meta: Dict[str, object] = {}  # 初始化 meta
    if meta_path.exists():  # 若存在 meta 文件
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))  # 解析 JSON
        except json.JSONDecodeError:  # 解析失败
            LOGGER.warning("wechat_meta_decode_failed", path=str(meta_path))  # 记录警告
    return {"plain_md": plain_md, "md_html": md_html, "meta": meta}  # 返回材料


def deliver_via_playwright(article: Dict, settings) -> DeliveryResult:  # 主入口
    """使用真实浏览器将草稿保存为公众号草稿。"""  # 中文说明

    title = article.get("title") or "未命名文章"  # 读取标题
    out_dir_raw = article.get("out_dir")  # 读取 outbox 路径
    if not out_dir_raw:  # 缺失路径
        raise ValueError("article 缺少 out_dir 字段")  # 抛出错误
    out_dir = Path(out_dir_raw)  # 转换为 Path
    material: Dict[str, object] = {"plain_md": "", "md_html": "", "meta": {}}  # 初始化材料
    try:  # 捕获读取异常
        material = _load_material(out_dir)  # 加载草稿
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("wechat_material_load_failed", path=str(out_dir), error=str(exc))  # 记录异常
        raise  # 无材料无法继续，抛出异常
    playwright = None  # 初始化 Playwright 引用
    browser = None  # 初始化浏览器引用
    context = None  # 初始化上下文
    trace_path: Optional[str] = None  # 记录 trace 路径
    screenshot_path: Optional[str] = None  # 记录截图
    try:  # 捕获整体异常
        playwright, browser = launch_browser(settings)  # 启动浏览器
        context = wechat_mp_bot.login_or_reuse_cookie(browser, settings)  # 登录或复用 Cookie
        trace_path = getattr(context, "_trace_path", None)  # 读取 trace 路径
        target_id = wechat_mp_bot.create_draft(  # 创建草稿
            context,
            settings,
            title,
            material["md_html"],
            material["plain_md"],
            material["meta"],
        )
        LOGGER.info("wechat_playwright_success", title=title, target_id=target_id)  # 记录成功
        return DeliveryResult(  # 构造成功结果
            platform="wechat_mp",
            status="success",
            target_id=target_id,
            out_dir=str(out_dir),
            payload={"meta": material["meta"]},
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("wechat_playwright_failed", title=title, error=str(exc))  # 记录异常
        if context and context.pages:  # 有页面时尝试截图
            try:
                screenshot_path = shoot(context.pages[-1], "wechat_failure", settings=settings)  # 截图
            except Exception:  # noqa: BLE001
                LOGGER.warning("wechat_screenshot_failed")  # 截图失败警告
        payload = {"meta": material.get("meta"), "screenshot": screenshot_path, "trace": trace_path}  # 失败上下文
        return DeliveryResult(  # 返回失败结果
            platform="wechat_mp",
            status="failed",
            target_id=None,
            out_dir=str(out_dir),
            payload=payload,
            error=str(exc),
        )
    finally:  # 结束时关闭浏览器并保存 trace
        if context and getattr(settings, "playwright_tracing", False):  # 若开启 tracing
            try:
                if trace_path:
                    context.tracing.stop(path=trace_path)  # 导出 trace
                else:
                    context.tracing.stop()  # 没有路径则停止
            except PlaywrightError:  # 停止异常
                LOGGER.warning("wechat_trace_stop_failed")  # 记录警告
        if playwright and browser:  # 关闭浏览器
            stop_browser(playwright, browser, context)  # 统一关闭
