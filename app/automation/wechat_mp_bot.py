"""微信公众号后台自动化 Bot，负责登录与草稿创建。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法

import json  # 解析页面返回的 JSON 文本
import time  # 等待扫码登录时使用
from pathlib import Path  # 处理路径
from typing import Optional  # 类型注解

import structlog  # 结构化日志
from playwright.sync_api import (  # Playwright 同步 API
    Browser,  # 浏览器类型
    BrowserContext,  # 上下文类型
    Error as PlaywrightError,  # 通用异常
    Page,  # 页面类型
    TimeoutError as PlaywrightTimeoutError,  # 超时异常
)

from app.automation.pw_helper import (  # 导入辅助函数
    ensure_dirs,  # 确保目录存在
    load_cookies,  # 加载 Cookie
    save_cookies,  # 保存 Cookie
    shoot,  # 截图
    with_timeout,  # 设置超时
)

LOGGER = structlog.get_logger(__name__)  # 初始化日志器
LOGIN_URL = "https://mp.weixin.qq.com/"  # 公众号后台入口
CREATE_URLS = [  # 常见的新建图文入口列表
    "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit",  # 编辑器直链
    "https://mp.weixin.qq.com/mp/appmsg/index?from=appmsg_create",  # 创作中心入口
]


def _start_context(browser: Browser, settings) -> BrowserContext:  # 创建上下文并按需开启 tracing
    """创建浏览器上下文，按配置加载 Cookie 并启动 tracing。"""  # 中文说明

    ensure_dirs(settings)  # 确保目录存在
    context = browser.new_context()  # 创建新的上下文
    if getattr(settings, "playwright_tracing", False):  # 若开启 tracing
        trace_dir = Path(getattr(settings, "logs_dir", Path("./logs"))) / "traces"  # 计算 trace 目录
        trace_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        trace_path = trace_dir / f"trace_wechat_{int(time.time())}.zip"  # 构造 trace 文件路径
        context.tracing.start(screenshots=True, snapshots=True)  # 启动 tracing
        setattr(context, "_trace_path", str(trace_path))  # 缓存路径供上层保存
    cookie_path = getattr(settings, "wechat_cookie_path", "./.sessions/wechat_mp.cookies.json")  # 解析 Cookie 路径
    try:  # 尝试加载 Cookie
        load_cookies(context, cookie_path)  # 加载 Cookie
    except Exception:  # noqa: BLE001
        LOGGER.warning("wechat_cookie_load_failed", path=cookie_path)  # 记录警告但不中断
    return context  # 返回上下文


def _wait_for_dashboard(page: Page, settings, timeout_ms: Optional[int] = None) -> bool:  # 检测是否进入后台
    """等待后台首页特征元素出现，判断是否登录成功。"""  # 中文说明

    actual_timeout = with_timeout(page, timeout_ms, settings=settings)  # 设置统一超时
    candidate_selectors = [  # 待匹配的特征元素
        "text=新建图文",  # 经典按钮
        "text=创作中心",  # 创作中心标题
        "text=素材管理",  # 素材库入口
    ]
    for selector in candidate_selectors:  # 遍历候选选择器
        try:  # 尝试等待元素
            page.wait_for_selector(selector, timeout=actual_timeout)  # 等待出现
            return True  # 找到即认为已登录
        except PlaywrightTimeoutError:  # 未找到继续尝试
            continue  # 尝试下一个
    return False  # 全部失败返回 False


def login_or_reuse_cookie(browser: Browser, settings) -> BrowserContext:  # 登录或复用 Cookie
    """尝试复用历史 Cookie 登录，如失败则提示扫码。"""  # 中文说明

    context = _start_context(browser, settings)  # 创建上下文并加载 Cookie
    page = context.new_page()  # 打开新页面
    with_timeout(page, settings=settings)  # 应用统一超时
    page.goto(LOGIN_URL, wait_until="domcontentloaded")  # 打开公众号后台
    if _wait_for_dashboard(page, settings, timeout_ms=5000):  # 先快速检查
        LOGGER.info("wechat_login_cookie_success")  # 记录成功
        return context  # 直接返回
    LOGGER.info("wechat_login_need_scan", message="请在 60 秒内扫码登录")  # 提示需扫码
    try:  # 等待扫码完成
        with_timeout(page, timeout_ms=60000, settings=settings)  # 加长超时
        page.wait_for_selector("text=扫码登录", timeout=2000)  # 尝试等待扫码提示出现
    except PlaywrightTimeoutError:  # 未出现扫码提示也继续
        LOGGER.debug("wechat_login_no_scan_prompt")  # 记录调试信息
    deadline = time.time() + 60  # 设定等待截止时间
    while time.time() < deadline:  # 循环等待
        if _wait_for_dashboard(page, settings, timeout_ms=2000):  # 每 2 秒检查一次
            try:  # 登录成功后保存 Cookie
                save_cookies(context, getattr(settings, "wechat_cookie_path", "./.sessions/wechat_mp.cookies.json"))  # 保存 Cookie
            except Exception:  # noqa: BLE001
                LOGGER.warning("wechat_cookie_save_failed")  # 记录警告
            return context  # 返回上下文
        time.sleep(2)  # 暂停后重试
    shoot(page, "wechat_login_timeout", settings=settings)  # 登录失败截图
    raise RuntimeError("公众号登录超时，请重试或手动扫码")  # 抛出异常


def _resolve_content_locator(page: Page, settings) -> Page:  # 定位编辑区域
    """尝试在主页面或 iframe 中定位富文本编辑器。"""  # 中文说明

    candidates = [  # 页面直接定位的候选
        page.locator("[contenteditable='true']").first,
        page.locator("div[role='textbox']").first,
    ]
    for locator in candidates:  # 遍历候选
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, settings=settings))
            return locator  # 返回找到的定位器
        except PlaywrightTimeoutError:
            continue  # 尝试下一个
    # iframe 兜底
    for frame_locator in [
        page.frame_locator("iframe.editor_iframe"),
        page.frame_locator("iframe[id*='ueditor']"),
        page.frame_locator("iframe"),
    ]:
        try:
            frame = frame_locator.first.frame  # 访问实际 frame
        except PlaywrightError:
            frame = None
        if frame is None:
            continue
        try:
            locator = frame.locator("[contenteditable='true']").first
            locator.wait_for(state="visible", timeout=with_timeout(page, settings=settings))
            return locator
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError("未能定位公众号编辑器")


def _fill_content(locator, page: Page, md_html: str, plain_md: str) -> None:  # 向编辑器写入内容
    """优先注入 HTML，失败后逐段插入纯文本。"""  # 中文说明

    try:
        locator.click()
        locator.evaluate("(el, html) => { el.innerHTML = html; }", md_html)
        return
    except PlaywrightError:
        LOGGER.debug("wechat_html_fill_failed")
    locator.click()
    segments = [seg.strip() for seg in plain_md.split("\n\n") if seg.strip()]
    for idx, segment in enumerate(segments):
        page.keyboard.insert_text(segment)
        if idx < len(segments) - 1:
            page.keyboard.press("Enter")
            page.keyboard.press("Enter")


def create_draft(
    context: BrowserContext,
    settings,
    title: str,
    md_html: str,
    plain_md: str,
    meta: Optional[dict] = None,
) -> Optional[str]:  # 创建公众号草稿
    """打开新建页面，填写标题与正文并保存草稿。"""  # 中文说明

    page = context.new_page()
    with_timeout(page, settings=settings)
    last_error: Optional[Exception] = None
    for url in CREATE_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded")
            break
        except PlaywrightTimeoutError as exc:
            last_error = exc
    else:
        raise RuntimeError(f"无法打开公众号新建页面: {last_error}")
    title_locators = [
        page.get_by_placeholder("请在此输入标题"),
        page.locator("input[placeholder*='标题']"),
        page.get_by_role("textbox", name="标题"),
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
        shoot(page, "wechat_title_not_found", settings=settings)
        raise RuntimeError("未能定位标题输入框")
    title_locator.fill("")
    title_locator.type(title)
    editor_locator = _resolve_content_locator(page, settings)
    _fill_content(editor_locator, page, md_html, plain_md)
    save_locators = [
        page.get_by_role("button", name="保存为草稿"),
        page.get_by_role("button", name="存为草稿"),
        page.locator("button:has-text('保存草稿')"),
        page.locator("text=保存为草稿"),
    ]
    clicked = False
    for locator in save_locators:
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, settings=settings))
            locator.click()
            clicked = True
            break
        except PlaywrightTimeoutError:
            continue
    if not clicked:
        shoot(page, "wechat_save_not_found", settings=settings)
        raise RuntimeError("未能找到保存草稿按钮")
    feedback_locators = [
        page.locator("text=保存成功"),
        page.locator("text=草稿箱"),
        page.locator("text=已保存"),
    ]
    saved = False
    for locator in feedback_locators:
        try:
            locator.wait_for(state="visible", timeout=with_timeout(page, timeout_ms=10000, settings=settings))
            saved = True
            break
        except PlaywrightTimeoutError:
            continue
    if not saved:
        LOGGER.warning("wechat_save_feedback_missing")
    target_id = None
    if "appmsgid=" in page.url:
        target_id = page.url.split("appmsgid=")[-1].split("&")[0]
    LOGGER.info("wechat_draft_saved", target_id=target_id, meta=json.dumps(meta or {}, ensure_ascii=False))
    try:
        save_cookies(context, getattr(settings, "wechat_cookie_path", "./.sessions/wechat_mp.cookies.json"))
    except Exception:
        LOGGER.warning("wechat_cookie_save_after_draft_failed")
    return target_id
