"""Playwright 自动化辅助函数集合。"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("automation")

T = TypeVar("T")


def _ensure_locator(page: Page, locator: str | Locator) -> Locator:
    """将字符串选择器转换为 Locator，便于统一处理。"""

    if isinstance(locator, Locator):
        return locator
    return page.locator(locator)


def _slugify_filename(name: str) -> str:
    """粗略地将标题转换为文件名，避免截图路径包含特殊字符。"""

    sanitized = "".join(ch if ch.isalnum() else "_" for ch in name)
    sanitized = "_".join(part for part in sanitized.split("_") if part)
    return sanitized or "automation"


def wait_and_fill(page: Page, selector: str | Locator, text: str, *, timeout: int = 15000) -> None:
    """等待元素出现后填入文本，兼容 input 与 textarea。"""

    target = _ensure_locator(page, selector)
    logger.debug("等待填写输入框 %s", selector)
    target.wait_for(state="visible", timeout=timeout)
    target.fill("")
    target.fill(text)


def wait_and_type_rich(page: Page, locator: str | Locator, text_md_or_html: str) -> None:
    """在富文本区域输入内容，自动区分 Markdown 与 HTML。"""

    target = _ensure_locator(page, locator)
    target.wait_for(state="visible", timeout=20000)
    target.click()
    handle = target.element_handle(timeout=2000)
    if handle is None:
        raise RuntimeError("富文本区域未找到有效元素句柄")
    # HTML 内容走粘贴事件；否则直接插入文本保持 Markdown 格式。
    content = text_md_or_html or ""
    if "<" in content and ">" in content:
        logger.debug("尝试通过粘贴事件写入 HTML 内容")
        try:
            page.evaluate(
                "(el, html) => {"
                "  el.focus();"
                "  try {"
                "    const data = new DataTransfer();"
                "    data.setData('text/html', html);"
                "    const evt = new ClipboardEvent('paste', {clipboardData: data});"
                "    el.dispatchEvent(evt);"
                "    return;"
                "  } catch (err) {"
                "    console.warn('DataTransfer 粘贴失败', err);"
                "  }"
                "  const ok = document.execCommand('insertHTML', false, html);"
                "  if (!ok) { el.innerHTML = html; }"
                "}",
                handle,
                content,
            )
            return
        except Exception:
            logger.exception("HTML 写入失败，继续以纯文本插入")
    page.keyboard.insert_text(content)


def safe_click(page: Page, selector: str | Locator, *, timeout: int = 10000) -> bool:
    """仅在元素存在时点击，失败时自动截图。"""

    target = _ensure_locator(page, selector)
    try:
        target.wait_for(state="attached", timeout=timeout)
        target.click()
        return True
    except PlaywrightTimeoutError:
        logger.debug("未在超时时间内找到可点击元素：%s", selector)
        return False
    except Exception as exc:  # pragma: no cover - Playwright 异常依赖环境
        logger.warning("点击元素 %s 失败：%s", selector, exc)
        save_screenshot(page, f"click_error_{_slugify_filename(str(selector))}.png")
        raise


def save_screenshot(page: Page, filename: str | None = None) -> Path:
    """保存当前页面截图到 automation_logs 目录并返回路径。"""

    date_dir = Path("automation_logs") / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        filename = f"automation_{int(time.time())}.png"
    path = date_dir / filename
    try:
        page.screenshot(path=path, full_page=True)
    except Exception as exc:  # pragma: no cover - 依赖浏览器环境
        logger.error("保存截图失败：%s", exc)
    return path


def retry(fn: Callable[[], T], *, tries: int = 3, delay_s: float = 1.5) -> T:
    """带指数退避的重试封装，便于处理偶发的网络抖动。"""

    last_exc: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - 异常因环境而异
            last_exc = exc
            if attempt == tries:
                raise
            sleep_time = delay_s * (2 ** (attempt - 1))
            logger.warning("第 %s 次尝试失败：%s，将在 %.1f 秒后重试", attempt, exc, sleep_time)
            time.sleep(sleep_time)
    raise last_exc  # pragma: no cover - 理论上不会执行


__all__ = [
    "retry",
    "safe_click",
    "save_screenshot",
    "wait_and_fill",
    "wait_and_type_rich",
]
