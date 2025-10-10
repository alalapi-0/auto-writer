"""平台投递适配器公共基类，内建限速、时间窗与混沌注入控制。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import random  # 生成抖动与混沌延迟
import threading  # 提供线程锁保障限速状态一致
import time  # 访问系统时间并执行睡眠
from abc import ABC, abstractmethod  # 引入抽象基类工具
from collections import deque  # 使用双端队列保存令牌时间戳
from datetime import datetime, timedelta, time as dt_time  # 处理时间窗逻辑
from typing import Callable, Deque, Dict, List, Optional, Tuple  # 类型提示集合
from zoneinfo import ZoneInfo  # 使用标准库时区支持

import structlog  # 结构化日志便于排障

from app.chaos.hooks import maybe_inject_chaos  # 引入混沌钩子
from app.telemetry.metrics import inc_rate_limit  # 引入 Prometheus 限速计数
from config.settings import settings  # 全局配置实例


LOGGER = structlog.get_logger(__name__)  # 初始化模块日志器


class RateLimiter:
    """实现滑动窗口限速与时间窗等待的组合控制器。"""  # 中文类文档

    def __init__(
        self,
        platform: str,
        limit_per_minute: int,
        jitter_range: Tuple[float, float],
        windows: List[str],
        timezone_name: str,
        sleep_func: Callable[[float], None] | None = None,
        monotonic_func: Callable[[], float] | None = None,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        """保存限速参数并初始化内部状态。"""  # 构造函数中文说明

        self.platform = platform  # 保存平台名称用于日志与指标
        self.limit_per_minute = max(0, limit_per_minute)  # 约束限速为非负整数
        self.jitter_range = jitter_range  # 存储投递前抖动区间
        self.windows = self._parse_windows(windows)  # 解析时间窗字符串为时间对象
        self.tz = ZoneInfo(timezone_name)  # 解析目标时区
        self._sleep = sleep_func or time.sleep  # 注入睡眠函数，默认使用 time.sleep
        self._monotonic = monotonic_func or time.monotonic  # 注入单调时间函数
        self._now = now_func or (lambda: datetime.now(self.tz))  # 注入当前时间函数
        self._lock = threading.Lock()  # 互斥锁保护时间戳队列
        self._recent: Deque[float] = deque()  # 保存一分钟内的调用时间戳

    @staticmethod
    def _parse_windows(windows: List[str]) -> List[Tuple[dt_time, dt_time]]:
        """将配置字符串解析为时间区间列表。"""  # 方法中文说明

        parsed: List[Tuple[dt_time, dt_time]] = []  # 初始化返回列表
        for raw in windows:  # 遍历所有时间窗配置
            if not raw or "-" not in raw:  # 缺失连字符时跳过
                continue  # 忽略非法配置
            start_raw, end_raw = raw.split("-", 1)  # 拆分起止时间
            try:  # 捕获解析异常
                start_hour, start_minute = [int(part) for part in start_raw.split(":", 1)]  # 解析起始时刻
                end_hour, end_minute = [int(part) for part in end_raw.split(":", 1)]  # 解析结束时刻
                start_time = dt_time(hour=start_hour, minute=start_minute)  # 构造起点时间对象
                end_time = dt_time(hour=end_hour, minute=end_minute)  # 构造终点时间对象
            except ValueError:  # 捕获格式异常
                continue  # 跳过非法配置
            parsed.append((start_time, end_time))  # 记录解析结果
        return parsed  # 返回时间窗列表

    def _seconds_until_window(self, now: datetime) -> float:
        """计算距下一个允许时间窗的秒数，位于窗口内时返回 0。"""  # 方法中文说明

        if not self.windows:  # 未配置时间窗时直接返回
            return 0.0  # 无需等待
        localized = now.astimezone(self.tz)  # 转换为目标时区
        current_time = localized.time()  # 提取当前时间
        for start, end in self.windows:  # 遍历所有时间窗
            if start <= end:  # 普通时间窗
                if start <= current_time <= end:  # 当前处于窗口内
                    return 0.0  # 无需等待
                if current_time < start:  # 窗口尚未开始
                    start_dt = localized.replace(
                        hour=start.hour,
                        minute=start.minute,
                        second=0,
                        microsecond=0,
                    )  # 构造当日窗口起点
                    return max(0.0, (start_dt - localized).total_seconds())  # 返回等待秒数
            else:  # 跨日时间窗
                if current_time >= start or current_time <= end:  # 命中跨日窗口
                    return 0.0  # 无需等待
        soonest: Optional[datetime] = None  # 记录最近窗口起点
        for start, end in self.windows:  # 再次遍历计算下次起点
            start_dt = localized.replace(
                hour=start.hour,
                minute=start.minute,
                second=0,
                microsecond=0,
            )  # 构造当日起点
            if start <= end and current_time < start:  # 当日未开始
                candidate = start_dt  # 候选起点即当日时间
            else:  # 当日已过或跨日窗口
                candidate = start_dt + timedelta(days=1)  # 推迟到次日
            if soonest is None or candidate < soonest:  # 更新最近起点
                soonest = candidate  # 保存候选
        if soonest is None:  # 兜底返回 0
            return 0.0  # 未找到窗口
        return max(0.0, (soonest - localized).total_seconds())  # 返回等待秒数

    def _drain_expired(self, now: float) -> None:
        """移除一分钟以前的调用记录，避免队列无限增长。"""  # 方法中文说明

        expire_before = now - 60.0  # 计算一分钟前的阈值
        while self._recent and self._recent[0] <= expire_before:  # 队列头部过期
            self._recent.popleft()  # 弹出过期时间戳

    def acquire(self) -> None:
        """阻塞直至满足时间窗与限速要求，然后追加随机抖动。"""  # 方法中文说明

        wait_for_window = self._seconds_until_window(self._now())  # 计算时间窗等待
        if wait_for_window > 0:  # 需要等待时间窗
            LOGGER.info(
                "delivery_window_wait", platform=self.platform, wait_seconds=wait_for_window
            )  # 记录时间窗等待日志
            inc_rate_limit(self.platform, "window")  # 上报时间窗等待指标
            self._sleep(wait_for_window)  # 阻塞等待直到窗口开启
        if self.limit_per_minute <= 0:  # 未配置限速或关闭
            self._apply_jitter()  # 仍然应用随机抖动
            return  # 直接返回
        while True:  # 循环直到获得配额
            with self._lock:  # 加锁保护队列
                now = self._monotonic()  # 读取当前单调时间
                self._drain_expired(now)  # 清理过期记录
                if len(self._recent) < self.limit_per_minute:  # 尚未达到限速
                    self._recent.append(now)  # 记录本次调用
                    break  # 获得配额
                earliest = self._recent[0]  # 读取最早时间戳
                wait_seconds = max(0.0, 60.0 - (now - earliest))  # 计算剩余等待时间
            if wait_seconds <= 0:  # 理论上应为正数
                continue  # 重新尝试
            LOGGER.warning(
                "delivery_rate_throttled", platform=self.platform, wait_seconds=wait_seconds
            )  # 记录限速日志
            inc_rate_limit(self.platform, "rate_limit")  # 上报限速指标
            self._sleep(wait_seconds)  # 等待令牌可用
        self._apply_jitter()  # 所有条件满足后施加抖动

    def _apply_jitter(self) -> None:
        """按照配置施加随机抖动，避免突发访问模式。"""  # 方法中文说明

        low, high = self.jitter_range  # 解构上下限
        if high <= 0 or high <= low:  # 抖动配置无效时直接返回
            return  # 无需抖动
        jitter = random.uniform(low, high)  # 生成随机等待时间
        LOGGER.debug(
            "delivery_jitter_sleep", platform=self.platform, wait_seconds=jitter
        )  # 记录抖动日志
        self._sleep(jitter)  # 执行抖动睡眠


class BaseDeliveryAdapter(ABC):
    """提供统一 deliver 入口并集成限速与混沌控制。"""  # 类中文说明

    platform_name: str = "unknown"  # 平台名称，子类需覆盖
    _limiter_lock = threading.Lock()  # 保护限速器字典
    _limiters: Dict[str, Optional[RateLimiter]] = {}  # 缓存各平台限速实例

    def deliver(self, article: Dict[str, str]) -> None:
        """投递文章前统一执行限速与混沌钩子，然后调用子类实现。"""  # 方法中文说明

        self.guard_rate_limit_for_platform(self.platform_name)  # 应用平台限速
        maybe_inject_chaos(f"delivery.{self.platform_name}")  # 在投递阶段注入混沌
        self._deliver(article)  # 调用子类实现具体逻辑

    @abstractmethod
    def _deliver(self, article: Dict[str, str]) -> None:
        """子类需覆盖的具体投递逻辑占位。"""  # 方法中文说明

        raise NotImplementedError  # 默认抛出异常提示子类实现

    @classmethod
    def guard_rate_limit_for_platform(cls, platform: str) -> None:
        """对任意平台执行限速控制，便于函数式适配器调用。"""  # 方法中文说明

        limiter = cls._get_limiter(platform)  # 获取限速器实例
        if limiter is None:  # 未配置限速
            BaseDeliveryAdapter._apply_global_jitter(platform)  # 仍可应用全局抖动
            return  # 直接返回
        limiter.acquire()  # 执行限速与时间窗等待

    @classmethod
    def _apply_global_jitter(cls, platform: str) -> None:
        """当平台未配置专属限速器时，根据全局抖动配置随机睡眠。"""  # 方法中文说明

        jitter = settings.delivery_jitter_sec  # 读取全局抖动配置
        if len(jitter) < 2:  # 配置不足时跳过
            return  # 不执行任何操作
        low, high = jitter[0], jitter[1]  # 解构上下限
        if high <= 0 or high <= low:  # 抖动配置非法
            return  # 不执行任何操作
        wait_seconds = random.uniform(low, high)  # 生成随机等待时间
        LOGGER.debug("delivery_global_jitter", platform=platform, wait_seconds=wait_seconds)  # 记录日志
        time.sleep(wait_seconds)  # 直接调用同步睡眠

    @classmethod
    def _get_limiter(cls, platform: str) -> Optional[RateLimiter]:
        """按需构建并缓存平台限速器。"""  # 方法中文说明

        with cls._limiter_lock:  # 加锁保护字典
            if platform in cls._limiters:  # 缓存命中
                return cls._limiters[platform]  # 返回缓存结果
            rate_map = getattr(settings, "delivery_rate_limit_per_platform", {})  # 读取限速配置
            limit_value = int(
                rate_map.get(platform, rate_map.get(platform.split("_", 1)[0], 0))
            )  # 获取平台限速数值并兼容别名
            windows_map = getattr(settings, "delivery_time_windows", {})  # 读取时间窗配置
            window_list = list(
                windows_map.get(platform, windows_map.get(platform.split("_", 1)[0], []))
            )  # 拷贝时间窗列表并兼容别名
            jitter = getattr(settings, "delivery_jitter_sec", [0, 0])  # 读取抖动配置
            jitter_range = (float(jitter[0]), float(jitter[1])) if len(jitter) >= 2 else (0.0, 0.0)  # 构造抖动元组
            tz_name = getattr(settings, "tz", "Asia/Tokyo")  # 读取时区，默认东京
            if limit_value <= 0 and not window_list:  # 限速与时间窗均未配置
                cls._limiters[platform] = None  # 缓存空值避免重复计算
                return None  # 返回空
            limiter = RateLimiter(  # 创建限速器实例
                platform=platform,
                limit_per_minute=limit_value,
                jitter_range=jitter_range,
                windows=window_list,
                timezone_name=tz_name,
            )  # 实例化结束
            cls._limiters[platform] = limiter  # 缓存实例
            return limiter  # 返回限速器
__all__ = ["BaseDeliveryAdapter", "RateLimiter"]  # 导出符号列表
