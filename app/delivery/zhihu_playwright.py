"""使用 Playwright 将草稿导入知乎专栏草稿箱。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法

import json  # 解析 meta 信息
from pathlib import Path  # 路径操作
from typing import Dict, Optional  # 类型注解

import structlog  # 结构化日志
from playwright.sync_api import Error as PlaywrightError  # Playwright 异常

from app.automation import zhihu_bot  # 导入知乎 Bot
from app.automation.pw_helper import launch_browser, shoot, stop_browser  # Playwright 工具
from app.delivery.types import DeliveryResult  # 返回类型

LOGGER = structlog.get_logger(__name__)  # 初始化日志器


def _load_material(out_dir: Path) -> Dict[str, object]:  # 读取草稿材料
    """读取 Markdown 与 meta 文件，返回统一字典。"""

    if not out_dir.exists():
        raise FileNotFoundError(f"知乎草稿目录不存在: {out_dir}")
    md_path = out_dir / "draft.md"
    meta_path = out_dir / "meta.json"
    plain_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    meta: Dict[str, object] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("zhihu_meta_decode_failed", path=str(meta_path))
    return {"plain_md": plain_md, "meta": meta}


def deliver_via_playwright(article: Dict, settings) -> DeliveryResult:
    """将本地草稿粘贴到知乎写作页面并保存。"""

    title = article.get("title") or "未命名文章"
    out_dir_raw = article.get("out_dir")
    if not out_dir_raw:
        raise ValueError("article 缺少 out_dir 字段")
    out_dir = Path(out_dir_raw)
    material: Dict[str, object] = {"plain_md": "", "meta": {}}
    try:
        material = _load_material(out_dir)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("zhihu_material_load_failed", path=str(out_dir), error=str(exc))
        raise
    playwright = None
    browser = None
    context = None
    trace_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    try:
        playwright, browser = launch_browser(settings)
        context = zhihu_bot.login_or_reuse_cookie(browser, settings)
        trace_path = getattr(context, "_trace_path", None)
        target_id = zhihu_bot.create_draft(
            context,
            settings,
            title,
            material["plain_md"],
            material["meta"],
        )
        LOGGER.info("zhihu_playwright_success", title=title, target_id=target_id)
        return DeliveryResult(
            platform="zhihu",
            status="success",
            target_id=target_id,
            out_dir=str(out_dir),
            payload={"meta": material["meta"]},
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("zhihu_playwright_failed", title=title, error=str(exc))
        if context and context.pages:
            try:
                screenshot_path = shoot(context.pages[-1], "zhihu_failure", settings=settings)
            except Exception:  # noqa: BLE001
                LOGGER.warning("zhihu_screenshot_failed")
        payload = {"meta": material.get("meta"), "screenshot": screenshot_path, "trace": trace_path}
        return DeliveryResult(
            platform="zhihu",
            status="failed",
            target_id=None,
            out_dir=str(out_dir),
            payload=payload,
            error=str(exc),
        )
    finally:
        if context and getattr(settings, "playwright_tracing", False):
            try:
                if trace_path:
                    context.tracing.stop(path=trace_path)
                else:
                    context.tracing.stop()
            except PlaywrightError:
                LOGGER.warning("zhihu_trace_stop_failed")
        if playwright and browser:
            stop_browser(playwright, browser, context)
