"""微信公众号草稿自动化流程。"""

from __future__ import annotations

import logging

from playwright.sync_api import BrowserContext, Frame, Page, TimeoutError as PlaywrightTimeoutError

from autowriter_text.pipeline.postprocess import ArticleRow

from .utils import retry, safe_click, save_screenshot, wait_and_fill

logger = logging.getLogger("automation.wechat")

_WECHAT_HOME = "https://mp.weixin.qq.com/"
_WECHAT_EDITOR = "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit"


class WeChatAutomator:
    """负责将导出的文章送入公众号草稿箱。"""

    def __init__(self, context: BrowserContext) -> None:
        self._context = context

    def create_draft(self, article: ArticleRow, *, screenshot_prefix: str | None = None) -> str:
        """为指定文章创建草稿并返回结果描述。"""

        def _task() -> str:
            page = self._context.new_page()
            try:
                return self._create_draft(page, article, screenshot_prefix=screenshot_prefix)
            finally:
                page.close()

        return retry(_task, tries=3, delay_s=2.0)

    def _create_draft(self, page: Page, article: ArticleRow, *, screenshot_prefix: str | None) -> str:
        logger.info("[wechat] 开始创建草稿：%s", article.title)
        page.set_default_timeout(20000)
        page.goto(_WECHAT_HOME, wait_until="domcontentloaded")
        if self._detect_manual_verification(page, article.title):
            raise RuntimeError("公众号后台需要人工验证或扫码登录，请处理后重试。")
        page.goto(_WECHAT_EDITOR, wait_until="domcontentloaded")
        self._dismiss_popups(page)
        self._fill_title(page, article)
        self._fill_content(page, article)
        self._save_draft(page, article, screenshot_prefix)
        return "保存草稿成功"

    def _detect_manual_verification(self, page: Page, title: str) -> bool:
        """检测是否进入验证码/扫码页面，若是则截图提醒人工处理。"""

        keywords = ["安全验证", "扫码登录", "请扫码登录", "验证登录"]
        for word in keywords:
            locator = page.locator(f"text={word}")
            try:
                if locator.first.is_visible(timeout=1000):
                    path = save_screenshot(page, f"wechat_verify_{self._slug(title)}.png")
                    logger.error("检测到验证页面，已保存截图：%s", path)
                    return True
            except PlaywrightTimeoutError:
                continue
        return False

    def _dismiss_popups(self, page: Page) -> None:
        """尝试关闭常见的引导与权限弹窗。"""

        for text in ["知道了", "确定", "继续访问", "允许"]:
            safe_click(page, f"text={text}", timeout=2000)

    def _fill_title(self, page: Page, article: ArticleRow) -> None:
        """多策略定位标题输入框。"""

        selectors = [
            "textarea[placeholder*='标题']",
            "textarea[aria-label*='标题']",
            "input[placeholder*='标题']",
            "input[aria-label*='标题']",
        ]
        for selector in selectors:
            try:
                wait_and_fill(page, selector, article.title)
                return
            except PlaywrightTimeoutError:
                continue
        raise RuntimeError("未能找到公众号标题输入框，请检查页面结构是否变更。")

    def _fill_content(self, page: Page, article: ArticleRow) -> None:
        """向富文本编辑器写入 HTML 正文。"""

        editor = self._locate_editor_frame(page)
        if editor is None:
            path = save_screenshot(page, f"wechat_editor_missing_{self._slug(article.title)}.png")
            raise RuntimeError(f"未找到公众号编辑器，已保存截图：{path}")
        try:
            editor.evaluate(
                "(html) => {"
                "  const editable = document.querySelector('div[contenteditable="true"]') || document.body;"
                "  if (!editable) { throw new Error('missing contenteditable'); }"
                "  editable.focus();"
                "  document.execCommand('selectAll', false, null);"
                "  const ok = document.execCommand('insertHTML', false, html);"
                "  if (!ok) { editable.innerHTML = html; }"
                "}",
                article.content_html,
            )
        except Exception as exc:
            logger.exception("写入正文失败：%s", exc)
            path = save_screenshot(page, f"wechat_fill_error_{self._slug(article.title)}.png")
            raise RuntimeError(f"无法写入正文，请手动粘贴。截图：{path}") from exc

    def _locate_editor_frame(self, page: Page) -> Frame | None:
        """尝试获取公众号编辑器所在的 frame。"""

        for frame in page.frames:
            url = frame.url or ""
            name = frame.name or ""
            if "appmsg_edit" in url or "ueditor" in name or "editor" in name:
                return frame
        return None

    def _save_draft(self, page: Page, article: ArticleRow, screenshot_prefix: str | None) -> None:
        """点击保存草稿并等待成功提示。"""

        button_selectors = [
            "button:has-text('保存为草稿')",
            "button:has-text('保存草稿')",
            "button:has-text('保存')",
            "text=保存草稿",
        ]
        for selector in button_selectors:
            if safe_click(page, selector, timeout=5000):
                break
        else:
            path = save_screenshot(page, f"wechat_save_missing_{self._slug(article.title)}.png")
            raise RuntimeError(f"未找到保存按钮，截图：{path}")
        success_texts = ["保存成功", "已保存至草稿箱", "保存草稿成功"]
        for text in success_texts:
            try:
                page.locator(f"text={text}").first.wait_for(state="visible", timeout=15000)
                logger.info("[wechat] 草稿保存成功：%s", article.title)
                return
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(
            page,
            f"{(screenshot_prefix or 'wechat')}_save_failed_{self._slug(article.title)}.png",
        )
        raise RuntimeError(f"未检测到保存成功提示，请查看截图：{path}")

    @staticmethod
    def _slug(title: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in title)[:50] or "article"


__all__ = ["WeChatAutomator"]
