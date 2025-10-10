"""RateLimiter 限速逻辑的单元测试。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解

from datetime import datetime  # 构造固定时间戳

from zoneinfo import ZoneInfo  # 引入时区用于窗口计算

from app.delivery.base import RateLimiter  # 引入被测限速器


def test_rate_limiter_enforces_per_minute_quota() -> None:
    """当一分钟内超过限额时应阻塞等待。"""  # 测试说明

    clock = {"now": 0.0}  # 模拟单调时间存储

    def fake_monotonic() -> float:
        """返回模拟单调时间。"""  # 内部函数说明

        return clock["now"]  # 读取当前时间

    sleeps: list[float] = []  # 记录睡眠时长

    def fake_sleep(seconds: float) -> None:
        """模拟睡眠并推进时间轴。"""  # 内部函数说明

        sleeps.append(seconds)  # 记录本次等待
        clock["now"] += seconds  # 推进单调时间

    now_func = lambda: datetime(2024, 1, 1, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # 固定窗口时间
    limiter = RateLimiter(  # 构造限速器
        platform="wechat",  # 平台名称
        limit_per_minute=2,  # 每分钟限额
        jitter_range=(0.0, 0.0),  # 关闭抖动
        windows=["00:00-23:59"],  # 全天窗口
        timezone_name="Asia/Shanghai",  # 时区
        sleep_func=fake_sleep,  # 注入假睡眠
        monotonic_func=fake_monotonic,  # 注入假时间
        now_func=now_func,  # 注入固定当前时间
    )
    limiter.acquire()  # 第一次调用不应等待
    limiter.acquire()  # 第二次调用仍在限额内
    limiter.acquire()  # 第三次触发限速
    assert sleeps == [60.0]  # 应等待 60 秒释放令牌


def test_rate_limiter_waits_for_window() -> None:
    """当当前时间不在窗口内时应等待至窗口开启。"""  # 测试说明

    sleeps: list[float] = []  # 记录等待

    def fake_sleep(seconds: float) -> None:
        """记录窗口等待时长。"""  # 内部函数说明

        sleeps.append(seconds)  # 保存等待值

    now_func = lambda: datetime(2024, 1, 1, 5, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # 当前时间 05:00
    limiter = RateLimiter(  # 构造限速器
        platform="wechat",  # 平台名称
        limit_per_minute=1,  # 限额
        jitter_range=(0.0, 0.0),  # 关闭抖动
        windows=["06:30-08:30"],  # 仅早间窗口
        timezone_name="Asia/Shanghai",  # 时区
        sleep_func=fake_sleep,  # 注入假睡眠
        monotonic_func=lambda: 0.0,  # 单调时间固定
        now_func=now_func,  # 注入当前时间
    )
    limiter.acquire()  # 尝试获取配额
    assert sleeps and abs(sleeps[0] - 5400) < 1  # 预计等待 1.5 小时
