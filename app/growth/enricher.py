"""事后热度补全策略占位实现。"""

from __future__ import annotations  # 启用未来注解

from typing import Iterable, List  # 类型标注


def enrich_keywords(consumed_keywords: Iterable[str], group_size: int) -> List[str]:
    """按照“每消耗 3 个补 3 个”的策略生成新关键词。"""

    consumed_list = [kw for kw in consumed_keywords if kw]  # 过滤空值
    if group_size <= 0:  # 守护条件
        group_size = 3  # 回退默认值
    new_keywords: List[str] = []  # 初始化结果列表
    for index in range(0, len(consumed_list), group_size):  # 按组遍历
        group = consumed_list[index : index + group_size]  # 切片获取一组
        if len(group) < group_size:  # 若不足整组
            break  # 暂不补充，等待下次运行
        batch_no = index // group_size + 1  # 计算组序号
        for offset, seed in enumerate(group, start=1):  # 遍历组内关键词
            candidate = f"{seed}心理延展{batch_no}-{offset}"  # 构造补充关键词
            new_keywords.append(candidate)  # 收录候选
        # TODO: 在生产环境通过外部热点源（如知乎热榜、豆瓣讨论）筛选候选关键词，并过滤偏题内容
    return new_keywords  # 返回补充结果
