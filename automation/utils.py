"""Playwright 自动化辅助函数集合。"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence, TypeVar

from playwright.sync_api import (
    ElementHandle,
    Frame,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger("automation")

T = TypeVar("T")


def _ensure_locator(page: Page, locator: str | Locator) -> Locator:
    """将字符串选择器转换为 Locator，便于统一处理。"""

    # 传入 Locator 时直接返回，避免重复创建。
    if isinstance(locator, Locator):
        return locator
    # 其它情况统一走 page.locator，保持行为一致。
    return page.locator(locator)


def _ensure_handle(target: Locator | ElementHandle) -> ElementHandle:
    """将 Locator 转换为 ElementHandle，便于在 Frame 上执行脚本。"""

    # Locator 时获取首个匹配元素的句柄。
    if isinstance(target, Locator):
        handle = target.element_handle(timeout=2000)
        if handle is None:
            raise RuntimeError("未能获取元素句柄用于后续操作")
        return handle
    # ElementHandle 直接返回，允许外部自行定位。
    return target


def _slugify_filename(name: str) -> str:
    """粗略地将标题转换为文件名，避免截图路径包含特殊字符。"""

    # 仅保留字母与数字，其余替换为下划线，降低文件系统兼容性问题。
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in name)
    # 连续下划线压缩，保持文件名简洁。
    sanitized = "_".join(part for part in sanitized.split("_") if part)
    return sanitized or "automation"


def human_sleep(min_s: float = 0.4, max_s: float = 1.2) -> None:
    """在两个动作之间加入随机停顿，模拟人工节奏。"""

    # 保护：最大值应不小于最小值，若不满足则取两者中的较大者。
    high = max(min_s, max_s)
    # 从区间内随机抽取停顿时长，避免固定节奏触发风控。
    delay = random.uniform(min_s, high)
    logger.debug("human sleep %.2f 秒", delay)
    # 调用 time.sleep 实际等待。
    time.sleep(delay)


def scroll_into_view(page: Page | Frame, selector_or_locator: str | Locator) -> None:
    """滚动页面使目标元素进入视窗，便于后续点击或输入。"""

    # Frame 没有 locator 方法，统一从 page 对象上获取。
    if isinstance(selector_or_locator, Locator):
        target = selector_or_locator
    elif isinstance(page, Frame):
        target = page.locator(selector_or_locator)
    else:
        target = _ensure_locator(page, selector_or_locator)
    # 等待元素出现，确保滚动不会抛异常。
    target.wait_for(state="attached", timeout=10000)
    handle = _ensure_handle(target)
    try:
        # Playwright 内置滚动方法，若元素本就可见也不会报错。
        handle.scroll_into_view_if_needed(timeout=2000)
    except Exception as exc:  # pragma: no cover - 浏览器环境相关
        logger.debug("scroll_into_view 失败：%s", exc)


def wait_and_fill(page: Page, selector: str | Locator, text: str, *, timeout: int = 15000) -> None:
    """等待元素出现后填入文本，兼容 input 与 textarea。"""

    # 将选择器转成 Locator，以便统一调用。
    target = _ensure_locator(page, selector)
    logger.debug("等待填写输入框 %s", selector)
    # 等待元素可见后再执行填充动作。
    target.wait_for(state="visible", timeout=timeout)
    target.fill("")  # 先清空旧值，避免残留内容。
    target.fill(text)  # 再填入新的文本内容。


def paste_html(editor: Locator | ElementHandle, html: str) -> None:
    """将 HTML 内容写入富文本区域，附带 innerHTML 兜底。"""

    # 将传入目标统一转换为 ElementHandle 以执行 DOM 操作。
    handle = _ensure_handle(editor)
    # owner_frame 可定位到对应的 Frame，便于处理 iframe 编辑器。
    frame = handle.owner_frame()
    if frame is None:
        raise RuntimeError("无法确定富文本所在的 Frame")
    # 执行脚本：focus + execCommand('insertHTML')，失败则回退到 innerHTML。
    frame.evaluate(
        "(el, html) => {"
        "  el.focus();"  # 聚焦编辑区域，确保后续命令生效。
        "  document.execCommand('selectAll', false, null);"  # 选中原有内容便于覆盖。
        "  const ok = document.execCommand('insertHTML', false, html);"  # 首选官方接口。
        "  if (!ok) {"
        "    // 注意：直接赋值 innerHTML 会失去事件监听，仅作为兜底使用。"
        "    el.innerHTML = html;"
        "  }"
        "}",
        handle,
        html or "",
    )


def insert_markdown(editor: Page | Frame | Locator | ElementHandle, md_text: str, chunk: int = 800) -> None:
    """以小块插入方式输入 Markdown，降低编辑器一次性粘贴失败概率。"""

    # 允许直接传入 Page/Frame，便于调用方灵活控制。
    if isinstance(editor, Page):
        # Page 级别时默认定位到 body，适配大多数富文本实现。
        target = editor.locator("body")
    elif isinstance(editor, Frame):
        # Frame 与 Page 类似，同样定位 body。
        target = editor.locator("body")
    else:
        # 传入 Locator/ElementHandle 时直接复用调用方结果。
        target = editor
    # 将目标统一转换成 ElementHandle，便于后续 focus 操作。
    handle = _ensure_handle(target) if isinstance(target, Locator) else target
    frame = handle.owner_frame()
    if frame is None:
        raise RuntimeError("未能获取 Markdown 编辑区域所属的 Frame")
    page = frame.page
    if page is None:
        raise RuntimeError("未能获取所属页面用于键盘输入")
    # 聚焦并清理历史内容，确保从空白状态开始输入。
    handle.scroll_into_view_if_needed(timeout=2000)
    frame.evaluate(
        "(el) => {"
        "  el.focus();"
        "  document.execCommand('selectAll', false, null);"
        "  document.execCommand('delete', false, null);"
        "}",
        handle,
    )
    # 将文本拆分为较小的块，避免一次 insert_text 过大导致丢字符。
    text = md_text or ""
    for start in range(0, len(text), max(1, chunk)):
        piece = text[start : start + max(1, chunk)]
        page.keyboard.insert_text(piece)
        # 每次插入后暂停片刻，模拟人工逐段输入。
        human_sleep(0.12, 0.28)


def wait_and_type_rich(page: Page, locator: str | Locator, text_md_or_html: str) -> None:
    """在富文本区域输入内容，自动区分 Markdown 与 HTML。"""

    # 先获取定位器并等待其可见。
    target = _ensure_locator(page, locator)
    target.wait_for(state="visible", timeout=20000)
    target.click()
    handle = target.element_handle(timeout=2000)
    if handle is None:
        raise RuntimeError("富文本区域未找到有效元素句柄")
    content = text_md_or_html or ""
    if "<" in content and ">" in content:
        logger.debug("尝试通过粘贴事件写入 HTML 内容")
        try:
            paste_html(handle, content)
            return
        except Exception:  # pragma: no cover - 依赖真实页面结构
            logger.exception("HTML 写入失败，继续以纯文本插入")
    insert_markdown(handle, content)


def safe_click(page: Page, selector: str | Locator, *, timeout: int = 10000) -> bool:
    """仅在元素存在时点击，失败时自动截图。"""

    target = _ensure_locator(page, selector)
    try:
        # 优先滚动到视窗中，避免被遮挡导致点击失败。
        handle = target.element_handle(timeout=timeout)
        if handle is not None:
            try:
                handle.scroll_into_view_if_needed(timeout=1500)
            except Exception:  # pragma: no cover - 滚动失败不影响主流程
                pass
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

    # 截图统一放到日期目录下，便于按天归档。
    date_dir = Path("automation_logs") / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        filename = f"automation_{int(time.time())}.png"
    path = date_dir / filename
    try:
        # full_page=True 便于排查页面整体状态。
        page.screenshot(path=path, full_page=True)
    except Exception as exc:  # pragma: no cover - 依赖浏览器环境
        logger.error("保存截图失败：%s", exc)
    return path


def preflight_check(page: Page, expected_patterns: Sequence[str]) -> bool:
    """检查页面是否包含预期文案，用于判断是否完成登录或进入正确页面。"""

    # 遍历关键字，任意一个可见即视为预检通过。
    for text in expected_patterns:
        locator = page.locator(f"text={text}")
        try:
            if locator.first.is_visible(timeout=1500):
                return True
        except PlaywrightTimeoutError:
            continue
    try:
        # 若元素不可见，再退化为全文本检索降低误判率。
        body_text = page.inner_text("body", timeout=2000)
    except Exception:
        body_text = ""
    normalized = body_text.replace("\n", "")
    return any(pattern in normalized for pattern in expected_patterns)


def retry(
    fn: Callable[[], T],
    *,
    tries: int = 3,
    delay_s: float = 1.5,
    backoff: float = 1.8,
) -> T:
    """带指数退避的重试封装，便于处理偶发的网络抖动。"""

    last_exc: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - 异常因环境而异
            last_exc = exc
            if attempt == tries:
                raise
            # 根据 backoff 指数衰减生成下一次重试的等待时长。
            sleep_time = delay_s * (backoff ** (attempt - 1))
            logger.warning("第 %s 次尝试失败：%s，将在 %.1f 秒后重试", attempt, exc, sleep_time)
            time.sleep(sleep_time)
    raise last_exc  # pragma: no cover - 理论上不会执行


__all__ = [
    "human_sleep",
    "insert_markdown",
    "paste_html",
    "preflight_check",
    "retry",
    "safe_click",
    "save_screenshot",
    "scroll_into_view",
    "wait_and_fill",
    "wait_and_type_rich",
]
