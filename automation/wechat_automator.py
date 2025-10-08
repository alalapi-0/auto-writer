"""微信公众号草稿自动化流程。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PlaywrightTimeoutError

from autowriter_text.pipeline.postprocess import ArticleRow

from .utils import (
    human_sleep,
    paste_html,
    preflight_check,
    retry,
    safe_click,
    save_screenshot,
    scroll_into_view,
    wait_and_fill,
)

logger = logging.getLogger("automation.wechat")

_WECHAT_HOME = "https://mp.weixin.qq.com/"


@dataclass(slots=True)
class AutomationFlowError(RuntimeError):
    """用于携带截图路径的异常类型。"""

    screenshot: str | None = None


def sanitize_for_wechat(html: str) -> str:
    """使用白名单规则清洗 HTML，确保公众号编辑器兼容。"""

    # 解析 HTML 时使用 html.parser，兼容性最佳且无需额外依赖。
    soup = BeautifulSoup(html or "", "html.parser")
    allowed_tags = {
        "p",
        "br",
        "strong",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "blockquote",
        "ul",
        "ol",
        "li",
        "img",
        "a",
        "code",
        "pre",
        "span",
    }
    allowed_attrs: dict[str, set[str]] = {
        "a": {"href", "title", "target", "rel"},
        "img": {"src", "alt"},
        "span": {"class"},
        "code": {"class"},
        "pre": {"class"},
    }
    # 遍历所有标签，处理白名单与属性控制。
    for tag in list(soup.find_all(True)):
        if tag.name not in allowed_tags:
            if tag.name in {"script", "style", "iframe"}:
                tag.decompose()
            else:
                tag.unwrap()
            continue
        allowed = allowed_attrs.get(tag.name, set())
        for attr in list(tag.attrs.keys()):
            if attr not in allowed:
                del tag.attrs[attr]
        if tag.name == "a":
            tag.attrs.setdefault("target", "_blank")
            tag.attrs.setdefault("rel", "noopener")
        if tag.name == "img":
            src = tag.get("src", "")
            if not src or not src.startswith(("http://", "https://")):
                placeholder = soup.new_tag("p")
                placeholder.string = "[TODO] 请手动上传图片并替换此处"
                tag.replace_with(placeholder)
                continue
        if tag.name in {"p", "span"} and not tag.get_text(strip=True) and not tag.find("img"):
            tag.decompose()
    # 移除多余的空行与空白，保持 HTML 紧凑。
    cleaned = str(soup).replace("\u200b", "").strip()
    return cleaned


class WeChatAutomator:
    """负责将导出的文章送入公众号草稿箱。"""

    def __init__(self, context: BrowserContext) -> None:
        self._context = context

    def create_draft(
        self,
        article: ArticleRow,
        *,
        screenshot_prefix: str | None = None,
        dry_run: bool = False,
        max_retries: int = 3,
    ) -> dict[str, object]:
        """尝试创建草稿，失败时返回结构化结果。"""

        result = {
            "ok": False,
            "platform": "wechat",
            "title": article.title,
            "reason": "",
            "screenshot": "",
        }

        # 内部任务：每次重试都新开页面，避免上一轮残留状态干扰。
        def _task() -> str:
            page = self._context.new_page()
            page.set_default_timeout(25000)
            try:
                return self._create_draft(page, article, screenshot_prefix, dry_run)
            finally:
                page.close()

        try:
            # 使用带指数退避的 retry 包装，增强稳定性。
            reason = retry(_task, tries=max_retries, delay_s=2.0, backoff=1.8)
        except AutomationFlowError as exc:
            result["reason"] = str(exc)
            if exc.screenshot:
                result["screenshot"] = exc.screenshot
        except Exception as exc:  # pragma: no cover - Playwright 行为依赖环境
            result["reason"] = str(exc)
        else:
            result["ok"] = True
            result["reason"] = reason
        return result

    def _create_draft(
        self,
        page: Page,
        article: ArticleRow,
        screenshot_prefix: str | None,
        dry_run: bool,
    ) -> str:
        logger.info("[wechat] 开始创建草稿：%s", article.title)
        try:
            # 预检：确保账号已登录，必要时提示人工介入。
            self._ensure_logged_in(page, article.title)
            # 打开「新建图文」编辑页。
            self._open_editor(page, article.title)
            # 关闭干扰弹窗，确保输入框可操作。
            self._dismiss_popups(page)
            # 填写标题，先清空再输入。
            self._fill_title(page, article.title)
            # 对正文做白名单清洗后写入。
            cleaned = sanitize_for_wechat(article.content_html)
            self._fill_content(page, article.title, cleaned)
            if dry_run:
                # dry-run 模式下不执行保存，直接返回提示。
                return "DRY RUN ✓"
            # 点击保存草稿并等待 Toast。
            self._save_draft(page, article.title, screenshot_prefix)
            return "保存草稿成功"
        except AutomationFlowError:
            raise
        except Exception as exc:  # pragma: no cover - 页面结构可能变化
            path = save_screenshot(page, f"wechat_unhandled_{self._slug(article.title)}.png")
            raise AutomationFlowError(
                f"公众号草稿创建异常，请查看截图：{path}", screenshot=str(path)
            ) from exc

    def _ensure_logged_in(self, page: Page, title: str) -> None:
        # 访问公众号首页，判断是否已进入后台。
        page.goto(_WECHAT_HOME, wait_until="domcontentloaded")
        patterns = ["新建图文", "写新图文", "图文素材"]
        if preflight_check(page, patterns):
            return
        # 未登录时保存截图并提示人工操作。
        path = save_screenshot(page, f"wechat_login_{self._slug(title)}.png")
        logger.warning("未检测到公众号后台登录状态，截图：%s", path)
        input("请在浏览器中完成登录后按回车继续…")
        page.wait_for_timeout(1000)
        # 完成登录后再尝试进入首页。
        page.goto(_WECHAT_HOME, wait_until="domcontentloaded")
        if not preflight_check(page, patterns):
            raise AutomationFlowError(
                "公众号后台仍未检测到登录状态，请重试。", screenshot=str(path)
            )

    def _open_editor(self, page: Page, title: str) -> None:
        # 多策略定位「新建图文」按钮，兼容不同布局。
        selectors = [
            "text=新建图文",
            "role=button[name*='新建']",
            "a[href*='appmsg']",
        ]
        for selector in selectors:
            try:
                # 滚动到按钮区域，避免被导航遮挡。
                scroll_into_view(page, selector)
                if safe_click(page, selector, timeout=5000):
                    try:
                        # 优先等待编辑器 URL 变化。
                        page.wait_for_url("**/appmsg_edit**", timeout=15000)
                    except PlaywrightTimeoutError:
                        # 如 URL 未变化则至少等待网络空闲。
                        page.wait_for_load_state("networkidle")
                    return
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(page, f"wechat_entry_{self._slug(title)}.png")
        raise AutomationFlowError("未能打开公众号编辑器，请检查入口。", screenshot=str(path))

    def _dismiss_popups(self, page: Page) -> None:
        # 逐一尝试点击常见弹窗按钮。
        for text in ["知道了", "确定", "继续访问", "允许"]:
            safe_click(page, f"text={text}", timeout=2000)

    def _fill_title(self, page: Page, title: str) -> None:
        # 通过占位符或 aria-label 匹配标题输入框。
        selectors = [
            "textarea[placeholder*='标题']",
            "input[placeholder*='标题']",
            "textarea[aria-label*='标题']",
            "input[aria-label*='标题']",
        ]
        for selector in selectors:
            try:
                scroll_into_view(page, selector)
                wait_and_fill(page, selector, title)
                human_sleep(0.3, 0.6)
                return
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(page, f"wechat_title_{self._slug(title)}.png")
        raise AutomationFlowError("未找到标题输入框，请检查页面结构。", screenshot=str(path))

    def _locate_editor(self, page: Page) -> Locator:
        # 先在主文档查找常见的 contenteditable 容器。
        editor_selectors: Iterable[str] = (
            "div[contenteditable='true']",
            "div.editor",
            "iframe[id*='ueditor']",
            "iframe[src*='ueditor']",
        )
        for selector in editor_selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="attached", timeout=5000)
            except PlaywrightTimeoutError:
                continue
            if "iframe" in selector:
                # iframe 需进一步获取内部正文容器。
                frame = locator.content_frame()
                if frame is None:
                    continue
                body = frame.locator("div[contenteditable='true']").first
                try:
                    body.wait_for(state="visible", timeout=5000)
                    return body
                except PlaywrightTimeoutError:
                    pass
                return frame.locator("body")
            return locator
        # 主文档无结果时遍历所有子 frame。
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            fallback = frame.locator("div[contenteditable='true']").first
            try:
                fallback.wait_for(state="visible", timeout=5000)
                return fallback
            except PlaywrightTimeoutError:
                continue
        raise AutomationFlowError("未找到公众号正文编辑区域，请手动检查。")

    def _fill_content(self, page: Page, title: str, html: str) -> None:
        try:
            editor = self._locate_editor(page)
        except AutomationFlowError as exc:
            path = save_screenshot(page, f"wechat_editor_{self._slug(title)}.png")
            raise AutomationFlowError("未找到公众号正文编辑区域，请查看截图。", screenshot=str(path)) from exc
        try:
            scroll_into_view(page, editor)
        except Exception:
            pass
        try:
            paste_html(editor, html)
            human_sleep(0.5, 0.8)
        except Exception as exc:
            path = save_screenshot(page, f"wechat_fill_{self._slug(title)}.png")
            raise AutomationFlowError("正文写入失败，请参考截图。", screenshot=str(path)) from exc

    def _save_draft(self, page: Page, title: str, screenshot_prefix: str | None) -> None:
        # 多种保存按钮选择器，兼容不同文案。
        buttons = [
            "button:has-text('保存为草稿')",
            "button:has-text('保存草稿')",
            "button:has-text('保存')",
            "text=保存草稿",
        ]
        for selector in buttons:
            if safe_click(page, selector, timeout=5000):
                break
        else:
            path = save_screenshot(page, f"wechat_save_btn_{self._slug(title)}.png")
            raise AutomationFlowError("未找到保存按钮，请检查页面。", screenshot=str(path))
        # 监听包含“保存成功”等文案的提示元素。
        confirm_texts = ["保存成功", "已保存至草稿箱", "保存草稿成功"]
        for text in confirm_texts:
            try:
                toast = page.locator(f"text={text}")
                toast.first.wait_for(state="visible", timeout=15000)
                human_sleep(0.6, 1.0)
                return
            except PlaywrightTimeoutError:
                continue
        path = save_screenshot(
            page,
            f"{(screenshot_prefix or 'wechat')}_save_failed_{self._slug(title)}.png",
        )
        raise AutomationFlowError("未检测到保存成功提示，请查看截图。", screenshot=str(path))

    @staticmethod
    def _slug(text: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in text)[:50] or "article"


__all__ = ["WeChatAutomator", "sanitize_for_wechat"]
