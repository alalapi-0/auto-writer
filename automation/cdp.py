"""连接到本机已打开的 Chrome 浏览器（CDP）。"""

from __future__ import annotations

import logging

from playwright.sync_api import BrowserContext, Error, sync_playwright

logger = logging.getLogger("automation.cdp")


def connect_chrome_cdp(cdp_url: str = "http://127.0.0.1:9222") -> BrowserContext:
    """使用 CDP 连接本机 Chrome，返回可复用的浏览器上下文。"""

    playwright = sync_playwright().start()
    try:
        # 使用 connect_over_cdp 复用已有的 Chrome，会继承登录态。
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Error as exc:
        playwright.stop()
        # 常见错误：Chrome 未按要求带 remote debugging 参数启动。
        raise RuntimeError(
            "无法通过 CDP 连接 Chrome，请确认已使用 --remote-debugging-port=9222 启动并保持打开。"
        ) from exc
    except Exception as exc:  # pragma: no cover - Playwright 报错依赖运行环境
        playwright.stop()
        # 其它未知失败时提示检查网络与端口占用情况。
        raise RuntimeError(
            "连接 Chrome 失败，请检查 remote debugging 端口是否可达。"
        ) from exc

    if browser.contexts:
        context = browser.contexts[0]
    else:
        context = browser.new_context()
    logger.info("已通过 CDP 连接到现有 Chrome 会话：%s", cdp_url)
    # 将 Playwright 实例挂在 context 上，便于调用方在结束后执行 stop() 释放资源。
    setattr(context, "_automation_playwright", playwright)
    return context


__all__ = ["connect_chrome_cdp"]
