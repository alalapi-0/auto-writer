"""Prompt 选择策略模块，支持轮询、权重及基于 Profile 的分流。"""

from __future__ import annotations  # 启用未来注解语法

import itertools  # 提供计数器实现轮询
import random  # 提供随机权重选择
from collections import defaultdict  # 构建默认计数器
from typing import Iterable, Mapping  # 类型提示

_ROUND_ROBIN_STATE = defaultdict(itertools.count)  # 存储不同 Variant 集合的轮询指针


def _normalize_key(variants: Iterable[str]) -> tuple[str, ...]:  # 辅助函数：构造轮询键
    """将 Variant 列表排序并转为元组，作为轮询状态的 key。"""  # 中文注释

    return tuple(sorted(variants))  # 排序后转元组确保确定性


def select_variant(  # 对外统一选择入口
    variants: list[str],  # 可用 Variant 列表
    profile_config: Mapping[str, object] | None,  # Profile 配置，可选
    strategy_config: Mapping[str, object] | None,  # 策略配置，可选
) -> str:  # 返回选中的 Variant 名称
    """根据策略配置返回一个 Prompt Variant。"""  # 中文注释

    if not variants:  # 若无可用 Variant
        raise ValueError("Variant 列表不能为空。")  # 抛出异常

    config = strategy_config or {}  # 读取策略配置
    strategy = (config.get("name") or "round_robin").lower()  # 默认轮询

    if strategy == "round_robin":  # 轮询策略
        key = _normalize_key(variants)  # 计算轮询 key
        counter = _ROUND_ROBIN_STATE[key]  # 获取对应计数器
        index = next(counter) % len(variants)  # 基于计数器取模得到索引
        return variants[index]  # 返回对应 Variant

    if strategy == "weighted":  # 权重策略
        weights = config.get("weights") or {}  # 读取权重配置
        pool: list[str] = []  # 构造重复列表用于随机选择
        for variant in variants:  # 遍历候选 Variant
            weight = float(weights.get(variant, 0))  # 获取权重，默认 0
            count = max(int(weight * 100), 0)  # 放大到整数次数
            pool.extend([variant] * count)  # 按权重扩充池
        if not pool:  # 若权重池为空
            pool = variants[:]  # 回退为等概率
        return random.choice(pool)  # 随机挑选

    if strategy == "by_profile":  # 基于 Profile 分流
        profile_mapping = config.get("profile_map") or {}  # 读取映射
        profile_key = None  # 初始化 Profile key
        if profile_config:  # 当传入 Profile 时尝试匹配
            profile_key = str(profile_config.get("name")) or str(profile_config.get("id"))  # 支持 name/id
        if profile_key and profile_key in profile_mapping:  # 若映射命中
            mapped = profile_mapping[profile_key]  # 取出对应配置
            if isinstance(mapped, str) and mapped in variants:  # 直接映射到 Variant
                return mapped  # 返回指定 Variant
            if isinstance(mapped, Mapping):  # 若映射为子策略
                return select_variant(variants, profile_config, mapped)  # 递归处理
        fallback = config.get("fallback")  # 读取兜底 Variant
        if isinstance(fallback, str) and fallback in variants:  # 若兜底存在
            return fallback  # 返回兜底 Variant
        return variants[0]  # 默认返回第一个 Variant

    if strategy == "traffic_split":  # 兼容别名：按流量百分比
        buckets = config.get("traffic") or {}  # 读取百分比分布
        roll = random.random()  # 生成 0-1 之间随机数
        cumulative = 0.0  # 累计概率
        last_variant = variants[-1]  # 兜底 Variant
        for variant in variants:  # 遍历候选 Variant
            pct = float(buckets.get(variant, 0))  # 获取概率值
            cumulative += pct  # 累加
            if roll <= cumulative:  # 若落在当前区间
                return variant  # 返回对应 Variant
        return last_variant  # 若未命中则返回最后一个

    return variants[0]  # 未识别策略时回退到第一个 Variant
