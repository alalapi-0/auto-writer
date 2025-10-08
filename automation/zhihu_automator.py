"""知乎草稿自动化流程。"""

from __future__ import annotations

import logging
from typing import Optional

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from autowriter_text.pipeline.postprocess import ArticleRow

from .utils import retry, safe_click, save_screenshot, wait_and_fill, wait_and_type_rich

logger = logging.getLogger("automation.zhihu")

_ZHIHU_WRITE = "https://zhuanlan.zhihu.com/write"


class ZhihuAutomator:
    """将文章内容同步到知乎写作页面。"""

    def __init__(self, context: BrowserContext) -> None:
        self._context = context

    def create_draft(self, article: ArticleRow, *, pause_on_login: bool = True) -> str:
        """新建或覆盖知乎草稿，返回结果描述。"""

        def _task() -> str:
            page = self._context.new_page()
            try:
                return self._create_draft(page, article, pause_on_login=pause_on_login)
            finally:
                page.close()

        return retry(_task, tries=3, delay_s=2.0)

    def _create_draft(self, page: Page, article: ArticleRow, *, pause_on_login: bool) -> str:
        logger.info("[zhihu] 开始创建草稿：%s", article.title)
        page.set_default_timeout(20000)
        page.goto(_ZHIHU_WRITE, wait_until="domcontentloaded")
        if pause_on_login and self._handle_login_or_captcha(page, article.title):
            logger.info("用户已完成登录，继续写入草稿。")
        self._fill_title(page, article.title)
        self._fill_content(page, article.content_md)
        link = self._save_draft(page, article.title)
        return link or "保存草稿成功"

    def _handle_login_or_captcha(self, page: Page, title: str) -> bool:
        """检测是否出现登录页或验证码，引导人工处理。"""

        if "signin" in page.url or "login" in page.url:
            path = save_screenshot(page, f"zhihu_login_{self._slug(title)}.png")
            logger.warning("检测到知乎登录页面，请在浏览器内完成登录后按回车继续。截图：%s", path)
            input("请在浏览器完成知乎登录后按回车继续…")
            page.wait_for_timeout(1500)
            return True
        captcha_texts = ["验证码", "安全验证", "请完成验证"]
        for text in captcha_texts:
            try:
                if page.locator(f"text={text}").first.is_visible(timeout=1000):
                    path = save_screenshot(page, f"zhihu_captcha_{self._slug(title)}.png")
                    logger.warning("检测到知乎验证码，请手动处理后按回车继续。截图：%s", path)
                    input("请处理知乎验证码后按回车继续…")
                    page.wait_for_timeout(1500)
                    return True
            except PlaywrightTimeoutError:
                continue
        return False

    def _fill_title(self, page: Page, title: str) -> None:
        """填写知乎文章标题。"""

        selectors = [
            "textarea[placeholder*='标题']",
            "textarea[aria-label*='标题']",
        ]
        for selector in selectors:
            try:
                wait_and_fill(page, selector, title)
                return
            except PlaywrightTimeoutError:
                continue
        # 新版知乎标题可能使用 div[role="textbox"]，退化为富文本输入方式。
        try:
            wait_and_type_rich(page, page.locator("div[role='textbox']").first, title)
            return
        except Exception:
            pass
        raise RuntimeError("未能找到知乎标题输入框，请确认页面是否改版。")

    def _fill_content(self, page: Page, markdown: str) -> None:
        """向知乎正文区域粘贴 Markdown 内容。"""

        editor_selectors = [
            "div[role='textbox'][contenteditable='true']",
            "div.EditorV2",
            "textarea",
        ]
        for selector in editor_selectors:
            try:
                wait_and_type_rich(page, selector, markdown)
                return
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(page, f"zhihu_editor_missing_{self._slug(markdown[:20])}.png")
        raise RuntimeError(f"未找到知乎正文区域，截图：{path}")

    def _save_draft(self, page: Page, title: str) -> Optional[str]:
        """点击保存按钮或等待自动保存提示。"""

        candidates = [
            "button:has-text('保存草稿')",
            "button:has-text('返回草稿箱')",
            "text=保存草稿",
        ]
        for selector in candidates:
            if safe_click(page, selector, timeout=4000):
                break
        indicators = ["已自动保存", "草稿已保存", "保存成功"]
        for text in indicators:
            try:
                page.locator(f"text={text}").first.wait_for(state="visible", timeout=15000)
                logger.info("[zhihu] 草稿保存成功：%s", title)
                return page.url
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(page, f"zhihu_save_failed_{self._slug(title)}.png")
        raise RuntimeError(f"知乎草稿保存未成功，请查看截图：{path}")

    @staticmethod
    def _slug(text: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in text)[:50] or "article"


__all__ = ["ZhihuAutomator"]
