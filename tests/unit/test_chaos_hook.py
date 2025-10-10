"""混沌注入钩子的单元测试。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解

import pytest  # 引入 pytest 辅助断言异常

from app.chaos.hooks import (  # 导入被测函数与异常
    ChaosDropError,
    ChaosError,
    maybe_inject_chaos,
    seed_rng,
)
from config.settings import settings  # 引入全局配置


def _snapshot_settings() -> tuple[bool, float, list[str]]:
    """保存当前混沌配置，方便测试结束后还原。"""  # 辅助函数说明

    return (
        getattr(settings, "chaos_enable", False),
        float(getattr(settings, "chaos_prob", 0.0)),
        list(getattr(settings, "chaos_types", [])),
    )


def _restore_settings(snapshot: tuple[bool, float, list[str]]) -> None:
    """将混沌配置恢复为测试前状态。"""  # 辅助函数说明

    settings.chaos_enable, settings.chaos_prob, settings.chaos_types = snapshot  # 解包还原


def test_latency_event_triggers_sleep() -> None:
    """当配置仅包含 latency 时应调用睡眠函数。"""  # 测试说明

    snapshot = _snapshot_settings()  # 保存原始配置
    try:
        settings.chaos_enable = True  # 开启混沌
        settings.chaos_prob = 1.0  # 确保触发
        settings.chaos_types = ["latency"]  # 只启用延迟
        seed_rng(7)  # 固定随机种子
        sleeps: list[float] = []  # 记录延迟值

        def fake_sleep(seconds: float) -> None:
            """记录延迟时长供断言使用。"""  # 内部函数说明

            sleeps.append(seconds)  # 保存延迟

        maybe_inject_chaos("test.stage", sleep_func=fake_sleep)  # 调用混沌钩子
        assert sleeps and 0.5 <= sleeps[0] <= 2.0  # 延迟值应在预设区间内
    finally:
        _restore_settings(snapshot)  # 恢复配置


def test_error_event_raises_exception() -> None:
    """当配置为 error 时应抛出 ChaosError。"""  # 测试说明

    snapshot = _snapshot_settings()  # 保存原始配置
    try:
        settings.chaos_enable = True  # 开启混沌
        settings.chaos_prob = 1.0  # 确保触发
        settings.chaos_types = ["error"]  # 只启用错误事件
        seed_rng(1)  # 设置随机种子
        with pytest.raises(ChaosError):  # 断言抛出 ChaosError
            maybe_inject_chaos("test.error")  # 调用混沌钩子
    finally:
        _restore_settings(snapshot)  # 恢复配置


def test_drop_event_raises_drop_error() -> None:
    """当配置为 drop 时应抛出 ChaosDropError。"""  # 测试说明

    snapshot = _snapshot_settings()  # 保存原始配置
    try:
        settings.chaos_enable = True  # 开启混沌
        settings.chaos_prob = 1.0  # 确保触发
        settings.chaos_types = ["drop"]  # 只启用丢弃事件
        seed_rng(2)  # 设置随机种子
        with pytest.raises(ChaosDropError):  # 断言抛出 ChaosDropError
            maybe_inject_chaos("test.drop")  # 调用混沌钩子
    finally:
        _restore_settings(snapshot)  # 恢复配置


def test_disabled_chaos_no_side_effect() -> None:
    """关闭开关时不应触发任何事件。"""  # 测试说明

    snapshot = _snapshot_settings()  # 保存原始配置
    try:
        settings.chaos_enable = False  # 关闭混沌
        settings.chaos_prob = 1.0  # 即便概率为 1 也不触发
        settings.chaos_types = ["latency"]  # 配置任意事件
        sleeps: list[float] = []  # 用于验证未调用

        def fake_sleep(seconds: float) -> None:
            """若被调用则向列表写入。"""  # 内部函数说明

            sleeps.append(seconds)  # 记录调用

        maybe_inject_chaos("test.disabled", sleep_func=fake_sleep)  # 调用混沌钩子
        assert not sleeps  # 未调用睡眠函数
    finally:
        _restore_settings(snapshot)  # 恢复配置
