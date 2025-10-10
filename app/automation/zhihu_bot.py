"""知乎专栏自动化 Bot，负责登录检测与草稿创建。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法

import json  # 序列化日志内容
import time  # 控制扫码等待
from pathlib import Path  # 路径操作
from typing import Optional  # 类型注解

import structlog  # 结构化日志
from playwright.sync_api import (  # Playwright 同步接口
    Browser,  # 浏览器类型
    BrowserContext,  # 上下文类型
    Page,  # 页面类型
    TimeoutError as PlaywrightTimeoutError,  # 超时异常
)

from app.automation.pw_helper import (  # 导入辅助工具
    ensure_dirs,  # 确保目录
    load_cookies,  # 加载 Cookie
    save_cookies,  # 保存 Cookie
    shoot,  # 截图
    with_timeout,  # 统一超时
)

LOGGER = structlog.get_logger(__name__)  # 初始化日志器
LOGIN_URL = "https://www.zhihu.com/"  # 知乎首页
WRITE_URL = "https://zhuanlan.zhihu.com/write"  # 写作入口


def _start_context(browser: Browser, settings) -> BrowserContext:  # 构造上下文
    """创建上下文、加载 Cookie，并按需开启 tracing。"""  # 中文说明

    ensure_dirs(settings)  # 保障目录
    context = browser.new_context()  # 新上下文
    if getattr(settings, "playwright_tracing", False):  # tracing 开关
        trace_dir = Path(getattr(settings, "logs_dir", Path("./logs"))) / "traces"  # trace 目录
        trace_dir.mkdir(parents=True, exist_ok=True)  # 确保存在
        trace_path = trace_dir / f"trace_zhihu_{int(time.time())}.zip"  # 生成文件名
        context.tracing.start(screenshots=True, snapshots=True)  # 开启 tracing
        setattr(context, "_trace_path", str(trace_path))  # 缓存路径
    cookie_path = getattr(settings, "zhihu_cookie_path", "./.sessions/zhihu.cookies.json")  # Cookie 路径
    try:  # 加载历史 Cookie
        load_cookies(context, cookie_path)  # 尝试加载
    except Exception:  # noqa: BLE001
        LOGGER.warning("zhihu_cookie_load_failed", path=cookie_path)  # 记录告警
    return context  # 返回上下文


def _is_logged_in(page: Page, settings, timeout_ms: Optional[int] = None) -> bool:  # 判定登录态
    """检测是否处于登录状态。"""  # 中文说明

    actual = with_timeout(page, timeout_ms, settings=settings)  # 计算超时
    signals = [  # 登录后的标志
        "text=创作者中心",
        "text=写文章",
        "text=发布文章",
        "text=我的草稿",
    ]
    for selector in signals:  # 遍历候选
        try:
            page.wait_for_selector(selector, timeout=actual)
            return True
        except PlaywrightTimeoutError:
            continue
    if "zhihu.com/signin" in page.url:
        return False
    return "登录" not in page.title()


def login_or_reuse_cookie(browser: Browser, settings) -> BrowserContext:  # 登录流程
    """复用 Cookie 或提示用户扫码登录知乎。"""  # 中文说明

    context = _start_context(browser, settings)  # 创建上下文
    page = context.new_page()  # 打开页面
    with_timeout(page, settings=settings)  # 设置超时
    page.goto(LOGIN_URL, wait_until="domcontentloaded")  # 打开首页
    if _is_logged_in(page, settings, timeout_ms=4000):  # 快速检查
        LOGGER.info("zhihu_login_cookie_success")
        return context
    LOGGER.info("zhihu_login_need_scan", message="请在 60 秒内完成登录验证")
    deadline = time.time() + 60
    while time.time() < deadline:
        if _is_logged_in(page, settings, timeout_ms=2000):
            try:
                save_cookies(context, getattr(settings, "zhihu_cookie_path", "./.sessions/zhihu.cookies.json"))
            except Exception:  # noqa: BLE001
                LOGGER.warning("zhihu_cookie_save_failed")
            return context
        time.sleep(2)
    shoot(page, "zhihu_login_timeout", settings=settings)
    raise RuntimeError("知乎登录超时，请重试")


def _focus_editor(page: Page, settings) -> Page:
    """查找并返回正文编辑区定位器。"""

    candidates = [
        page.locator("div.DraftEditor-root [contenteditable='true']").first,
        page.locator("div[contenteditable='true']").first,
        page.locator("div[role='textbox']").first,
    ]
    for locator in candidates:
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, settings=settings))
            locator.click()
            return locator
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError("未能定位知乎编辑器")


def create_draft(
    context: BrowserContext,
    settings,
    title: str,
    plain_md: str,
    meta: Optional[dict] = None,
) -> Optional[str]:
    """在知乎写作页创建草稿。"""

    page = context.new_page()
    with_timeout(page, settings=settings)
    page.goto(WRITE_URL, wait_until="domcontentloaded")
    title_locators = [
        page.get_by_placeholder("输入标题"),
        page.locator("textarea[placeholder*='标题']"),
        page.locator("textarea").first,
    ]
    title_locator = None
    for locator in title_locators:
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, settings=settings))
            title_locator = locator
            break
        except PlaywrightTimeoutError:
            continue
    if title_locator is None:
        shoot(page, "zhihu_title_not_found", settings=settings)
        raise RuntimeError("未能定位知乎标题输入框")
    title_locator.fill("")
    title_locator.type(title)
    editor_locator = _focus_editor(page, settings)
    segments = [seg.strip() for seg in plain_md.split("\n\n") if seg.strip()]
    for idx, segment in enumerate(segments):
        page.keyboard.insert_text(segment)
        if idx < len(segments) - 1:
            page.keyboard.press("Enter")
            page.keyboard.press("Enter")
    save_locators = [
        page.get_by_role("button", name="保存草稿"),
        page.get_by_role("button", name="已保存"),
        page.locator("button:has-text('保存草稿')"),
    ]
    for locator in save_locators:
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, timeout_ms=5000, settings=settings))
            locator.click()
            break
        except PlaywrightTimeoutError:
            continue
    feedback_locators = [
        page.locator("text=草稿已保存"),
        page.locator("text=已保存"),
    ]
    for locator in feedback_locators:
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, timeout_ms=5000, settings=settings))
            break
        except PlaywrightTimeoutError:
            continue
    target_id = None
    if "/draft/" in page.url:
        target_id = page.url.split("/draft/")[-1].split("?")[0]
    LOGGER.info("zhihu_draft_saved", target_id=target_id, meta=json.dumps(meta or {}, ensure_ascii=False))
    try:
        save_cookies(context, getattr(settings, "zhihu_cookie_path", "./.sessions/zhihu.cookies.json"))
    except Exception:  # noqa: BLE001
        LOGGER.warning("zhihu_cookie_save_after_draft_failed")
    return target_id
