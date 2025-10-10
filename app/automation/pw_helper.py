"""Playwright 辅助工具，统一封装目录、浏览器与截图逻辑。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法提高兼容性

import json  # 序列化与反序列化 Cookie 文件
import os  # 处理权限与环境变量
from datetime import datetime  # 生成时间戳用于截图命名
from pathlib import Path  # 统一路径操作
from typing import Any, Optional, Tuple  # 类型注解辅助

import structlog  # 引入结构化日志
from playwright.sync_api import (  # 导入 Playwright 同步接口
    Browser,  # 浏览器实例类型
    BrowserContext,  # 浏览器上下文类型
    Error as PlaywrightError,  # Playwright 通用异常
    Page,  # 页面对象类型
    Playwright,  # Playwright 引擎对象
    sync_playwright,  # 启动 Playwright 的同步入口
)

LOGGER = structlog.get_logger(__name__)  # 初始化模块级日志器
_CURRENT_SETTINGS = None  # 全局缓存 settings，便于工具函数复用


def _resolve_settings(settings) -> Any:  # 内部函数：解析 settings 引用
    """优先使用入参 settings，缺省时使用 ensure_dirs 缓存的设置。"""  # 中文说明

    if settings is not None:  # 若调用方传入设置
        return settings  # 直接返回
    if _CURRENT_SETTINGS is None:  # 若未缓存设置
        raise RuntimeError("settings 未初始化，请先调用 ensure_dirs")  # 抛出错误提示调用顺序
    return _CURRENT_SETTINGS  # 返回缓存配置


def ensure_dirs(settings) -> None:  # 创建会话目录与截图目录
    """根据配置创建 Playwright 相关目录，并设置权限。"""  # 中文说明

    global _CURRENT_SETTINGS  # 使用全局缓存
    _CURRENT_SETTINGS = settings  # 缓存 settings 供其他函数读取
    session_dir = Path(getattr(settings, "session_dir", "./.sessions"))  # 解析会话目录
    screenshot_dir = Path(getattr(settings, "playwright_screenshot_dir", "./logs/screenshots"))  # 解析截图目录
    try:  # 捕获可能的文件系统异常
        session_dir.mkdir(parents=True, exist_ok=True)  # 创建会话目录
        os.chmod(session_dir, 0o700)  # 设置权限为 700 保护 Cookie
    except Exception as exc:  # noqa: BLE001  # 捕获所有异常并记录
        LOGGER.exception("创建会话目录失败", path=str(session_dir), error=str(exc))  # 输出错误日志
        raise  # 向上抛出异常
    try:  # 创建截图目录
        screenshot_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        os.chmod(screenshot_dir, 0o755)  # 截图目录设置为可读权限
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("创建截图目录失败", path=str(screenshot_dir), error=str(exc))  # 输出错误日志
        raise  # 向上抛出


def launch_browser(settings) -> Tuple[Playwright, Browser]:  # 启动浏览器并返回 Playwright 与 Browser
    """根据配置启动 Chromium 浏览器。"""  # 中文说明

    ensure_dirs(settings)  # 先确保目录存在
    try:  # 捕获启动异常
        playwright = sync_playwright().start()  # 启动 Playwright 引擎
        browser = playwright.chromium.launch(  # 启动 Chromium 浏览器
            headless=bool(getattr(settings, "playwright_headless", True)),  # 按配置决定是否无头
            slow_mo=int(getattr(settings, "playwright_slowmo_ms", 0)) or 0,  # 设置慢动作延迟
        )
        LOGGER.info(
            "browser_launch_success",  # 日志事件名称
            headless=getattr(settings, "playwright_headless", True),  # 记录无头配置
            slow_mo=getattr(settings, "playwright_slowmo_ms", 0),  # 记录慢动作配置
        )
        return playwright, browser  # 返回实例供调用方使用
    except PlaywrightError as exc:  # 捕获 Playwright 专用异常
        LOGGER.exception("启动浏览器失败", error=str(exc))  # 记录失败
        raise  # 抛出给上层处理


def load_cookies(context: BrowserContext, cookie_path: str) -> None:  # 加载 Cookie 文件
    """尝试从 JSON 文件加载 Cookie 到上下文。"""  # 中文说明

    path = Path(cookie_path)  # 转为 Path 对象
    if not path.exists():  # 文件不存在
        LOGGER.info("cookie_file_missing", path=str(path))  # 记录信息
        return  # 无需继续
    try:  # 尝试读取 Cookie 文件
        data = json.loads(path.read_text(encoding="utf-8"))  # 读取并解析 JSON
        if isinstance(data, dict) and "cookies" in data:  # Playwright 官方导出结构
            cookies = data.get("cookies", [])  # 读取 cookies 数组
        else:  # 兼容直接写入 cookies 数组的格式
            cookies = data  # 直接使用原数据
        if cookies:  # 若有数据
            context.add_cookies(cookies)  # 注入 Cookie
            LOGGER.info("cookie_loaded", path=str(path), count=len(cookies))  # 记录数量
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("加载 Cookie 失败", path=str(path), error=str(exc))  # 记录错误
        raise  # 抛出异常供上层处理


def save_cookies(context: BrowserContext, cookie_path: str) -> None:  # 保存当前 Cookie
    """从上下文导出 Cookie 并写入 JSON 文件。"""  # 中文说明

    path = Path(cookie_path)  # 转换为 Path
    try:  # 捕获写入异常
        path.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在
        cookies = context.cookies()  # 读取当前 Cookie 列表
        payload = json.dumps({"cookies": cookies}, ensure_ascii=False, indent=2)  # 序列化 JSON
        path.write_text(payload, encoding="utf-8")  # 写入文件
        os.chmod(path, 0o600)  # Cookie 文件权限设为 600
        LOGGER.info("cookie_saved", path=str(path), count=len(cookies))  # 记录成功
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("保存 Cookie 失败", path=str(path), error=str(exc))  # 记录错误
        raise  # 抛出异常


def shoot(page: Page, tag: str, settings=None) -> str:  # 截图并返回路径
    """以 tag+时间戳命名截图，方便排障。"""  # 中文说明

    cfg = _resolve_settings(settings)  # 获取配置
    screenshot_dir = Path(getattr(cfg, "playwright_screenshot_dir", "./logs/screenshots"))  # 解析截图目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # 生成时间戳
    filename = f"{tag}_{timestamp}.png"  # 构造文件名
    target_path = screenshot_dir / filename  # 组合完整路径
    try:  # 捕获截图异常
        page.screenshot(path=str(target_path), full_page=True)  # 保存全页截图
        LOGGER.info("screenshot_saved", path=str(target_path))  # 记录成功
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("截图失败", tag=tag, error=str(exc))  # 记录失败
        raise  # 抛出异常
    return str(target_path)  # 返回路径字符串


def with_timeout(page_or_locator, timeout_ms: Optional[int] = None, settings=None) -> int:  # 设置统一超时
    """为页面或定位器设置默认超时，返回最终毫秒值。"""  # 中文说明

    cfg = _resolve_settings(settings)  # 获取配置
    actual = int(timeout_ms if timeout_ms is not None else getattr(cfg, "playwright_timeout_ms", 30000))  # 计算最终超时
    if hasattr(page_or_locator, "set_default_timeout"):  # 若对象支持 set_default_timeout（Page）
        page_or_locator.set_default_timeout(actual)  # 设置默认超时
    elif hasattr(page_or_locator, "set_timeout"):  # 若为 Locator
        page_or_locator.set_timeout(actual)  # 设置定位器超时
    return actual  # 返回结果供调用方参考


def stop_browser(playwright: Playwright, browser: Browser, context: Optional[BrowserContext] = None) -> None:  # 关闭浏览器
    """优雅关闭浏览器与 Playwright 引擎。"""  # 中文说明

    try:  # 优雅关闭上下文
        if context is not None:  # 若传入上下文
            context.close()  # 关闭上下文
        browser.close()  # 关闭浏览器
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("关闭浏览器时出错", error=str(exc))  # 记录警告但不阻断
    finally:  # 无论成功与否都需停止引擎
        try:  # 捕获停止异常
            playwright.stop()  # 停止 Playwright
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("停止 Playwright 失败", error=str(exc))  # 记录警告
