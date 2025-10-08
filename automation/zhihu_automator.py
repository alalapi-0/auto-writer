"""知乎草稿自动化流程。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PlaywrightTimeoutError

from autowriter_text.pipeline.postprocess import ArticleRow

from .utils import (
    human_sleep,
    insert_markdown,
    preflight_check,
    retry,
    safe_click,
    save_screenshot,
    scroll_into_view,
    wait_and_fill,
    wait_and_type_rich,
)

logger = logging.getLogger("automation.zhihu")

_ZHIHU_WRITE = "https://zhuanlan.zhihu.com/write"


@dataclass(slots=True)
class AutomationFlowError(RuntimeError):
    """用于捕获异常路径并携带截图信息。"""

    screenshot: str | None = None


class ZhihuAutomator:
    """将文章内容同步到知乎写作页面。"""

    def __init__(self, context: BrowserContext) -> None:
        self._context = context

    def create_draft(
        self,
        article: ArticleRow,
        *,
        dry_run: bool = False,
        max_retries: int = 3,
    ) -> dict[str, object]:
        """新建或覆盖知乎草稿，返回结构化结果。"""

        result = {
            "ok": False,
            "platform": "zhihu",
            "title": article.title,
            "reason": "",
            "screenshot": "",
        }

        # 内部任务：每轮重试都单独开页，避免历史状态干扰。
        def _task() -> str:
            page = self._context.new_page()
            page.set_default_timeout(25000)
            try:
                return self._create_draft(page, article, dry_run)
            finally:
                page.close()

        try:
            # 使用 retry 提高稳定性，网络抖动时自动退避。
            reason = retry(_task, tries=max_retries, delay_s=2.0, backoff=1.8)
        except AutomationFlowError as exc:
            result["reason"] = str(exc)
            if exc.screenshot:
                result["screenshot"] = exc.screenshot
        except Exception as exc:  # pragma: no cover - Playwright 环境相关
            result["reason"] = str(exc)
        else:
            result["ok"] = True
            result["reason"] = reason
        return result

    def _create_draft(self, page: Page, article: ArticleRow, dry_run: bool) -> str:
        logger.info("[zhihu] 开始创建草稿：%s", article.title)
        try:
            # 打开写作页面，必要时提示人工登录或过验证码。
            self._ensure_write_page(page, article.title)
            # 填写标题。
            self._fill_title(page, article.title)
            # 写入 Markdown 正文。
            self._fill_content(page, article.content_md)
            if dry_run:
                # dry-run 模式不执行保存，仅验证流程。
                return "DRY RUN ✓"
            # 保存草稿或等待自动保存提示。
            self._save_draft(page, article.title)
            return "保存草稿成功"
        except AutomationFlowError:
            raise
        except Exception as exc:  # pragma: no cover - 页面细节可能变化
            path = save_screenshot(page, f"zhihu_unhandled_{self._slug(article.title)}.png")
            raise AutomationFlowError("知乎草稿创建异常，请查看截图。", screenshot=str(path)) from exc

    def _ensure_write_page(self, page: Page, title: str) -> None:
        # 打开知乎写作页面，判断是否被重定向到登录页。
        page.goto(_ZHIHU_WRITE, wait_until="domcontentloaded")
        if "login" in page.url or "signin" in page.url:
            path = save_screenshot(page, f"zhihu_login_{self._slug(title)}.png")
            logger.warning("检测到知乎登录页面，截图：%s", path)
            input("请在该浏览器完成登录后按回车继续…")
            page.wait_for_timeout(1200)
            page.goto(_ZHIHU_WRITE, wait_until="domcontentloaded")
        # 检测验证码拦截。
        patterns = ["写文章", "发布文章", "草稿箱"]
        captcha_texts = ["验证码", "安全验证", "请完成验证"]
        if any(self._text_visible(page, text) for text in captcha_texts):
            path = save_screenshot(page, f"zhihu_captcha_{self._slug(title)}.png")
            logger.warning("检测到知乎验证码，截图：%s", path)
            input("请完成验证码后按回车继续…")
            page.wait_for_timeout(1200)
            page.goto(_ZHIHU_WRITE, wait_until="domcontentloaded")
        # 预检：页面中出现核心文案视为成功。
        if not preflight_check(page, patterns):
            path = save_screenshot(page, f"zhihu_preflight_{self._slug(title)}.png")
            raise AutomationFlowError("知乎写作页预检失败，请人工确认。", screenshot=str(path))

    def _text_visible(self, page: Page, text: str) -> bool:
        locator = page.locator(f"text={text}")
        try:
            return locator.first.is_visible(timeout=1000)
        except PlaywrightTimeoutError:
            return False

    def _fill_title(self, page: Page, title: str) -> None:
        # 优先使用 textarea/input 类型的标题输入框。
        selectors = [
            "textarea[placeholder*='标题']",
            "[data-testid*='PostEditor-Title'] textarea",
            "input[placeholder*='标题']",
        ]
        for selector in selectors:
            try:
                scroll_into_view(page, selector)
                wait_and_fill(page, selector, title)
                human_sleep(0.3, 0.6)
                return
            except PlaywrightTimeoutError:
                continue
        # 新版编辑器可能使用富文本 div 作为标题。
        rich_title = page.locator("div[role='textbox']").first
        try:
            wait_and_type_rich(page, rich_title, title)
            human_sleep(0.3, 0.6)
            return
        except Exception as exc:
            path = save_screenshot(page, f"zhihu_title_{self._slug(title)}.png")
            raise AutomationFlowError("未找到知乎标题输入框，请检查。", screenshot=str(path)) from exc

    def _locate_editor(self, page: Page) -> Locator:
        # 按常见容器顺序查找正文编辑器。
        selectors: Iterable[str] = (
            "div[contenteditable='true']",
            "[data-testid*='PostEditor-Content']",
            "div.EditorV2",
        )
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=6000)
                return locator
            except PlaywrightTimeoutError:
                continue
        raise AutomationFlowError("未找到知乎正文编辑区域，请关注页面改动。")

    def _fill_content(self, page: Page, markdown: str) -> None:
        try:
            editor = self._locate_editor(page)
        except AutomationFlowError as exc:
            path = save_screenshot(page, f"zhihu_editor_{self._slug(markdown[:20])}.png")
            raise AutomationFlowError("未找到知乎正文编辑区域，请查看截图。", screenshot=str(path)) from exc
        try:
            scroll_into_view(page, editor)
        except Exception:
            pass
        try:
            # 先尝试一次性粘贴，最快捷。
            editor.click()
            editor.press("Control+A")
            editor.press("Delete")
            page.keyboard.insert_text(markdown)
            human_sleep(0.5, 0.8)
        except Exception:
            logger.info("一次性粘贴失败，尝试分段插入 Markdown。")
            try:
                # 分段 insert_markdown，降低失败概率。
                insert_markdown(editor, markdown)
            except Exception as exc:
                path = save_screenshot(page, f"zhihu_content_{self._slug(markdown[:20])}.png")
                raise AutomationFlowError("知乎正文写入失败，请查看截图。", screenshot=str(path)) from exc

    def _save_draft(self, page: Page, title: str) -> None:
        # 先尝试显式保存按钮。
        buttons = [
            "button:has-text('保存草稿')",
            "button:has-text('返回草稿箱')",
            "text=保存草稿",
        ]
        for selector in buttons:
            if safe_click(page, selector, timeout=4000):
                human_sleep(0.4, 0.8)
                break
        # 监听提示文案，确认保存状态。
        indicators = ["已自动保存", "草稿已保存", "保存成功"]
        for text in indicators:
            try:
                page.locator(f"text={text}").first.wait_for(state="visible", timeout=15000)
                human_sleep(0.4, 0.8)
                return
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(page, f"zhihu_save_{self._slug(title)}.png")
        raise AutomationFlowError("知乎草稿保存未成功，请查看截图。", screenshot=str(path))

    @staticmethod
    def _slug(text: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in text)[:50] or "article"


__all__ = ["ZhihuAutomator"]
