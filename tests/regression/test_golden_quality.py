"""黄金集回归测试，确保离线样例维持既有结构与风格。"""

from __future__ import annotations  # 使用未来注解以保持类型一致

import json  # 读取黄金集样本
from pathlib import Path  # 扫描测试目录

import pytest  # 测试框架

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"  # 黄金集目录


@pytest.mark.parametrize("case_path", sorted(GOLDEN_DIR.glob("*.json")))
def test_golden_samples(case_path: Path) -> None:
    """逐条校验黄金集样本的结构特征。"""  # 中文注释说明测试目标

    payload = json.loads(case_path.read_text(encoding="utf-8"))  # 读取样本
    mock_output = payload["mock_output"]  # 模拟生成结果
    expected = payload["expected"]  # 读取期望特征

    title = mock_output["title"]
    assert title.startswith(expected["title_prefix"])  # 标题需满足前缀约束

    body = mock_output["body"].strip()
    paragraphs = [p for p in body.split("\n\n") if p.strip()]  # 粗略统计段落数
    min_p, max_p = expected["paragraph_range"]
    assert min_p <= len(paragraphs) <= max_p  # 断言段落数处于目标区间

    for keyword in expected["must_keywords"]:
        assert keyword in body, f"缺少关键词: {keyword}"  # 正文需覆盖核心关键词

    summary = mock_output.get("summary", "")
    for keyword in expected.get("summary_keywords", []):
        assert keyword in summary, f"摘要缺少关键词: {keyword}"  # 摘要覆盖关键词

    tags = mock_output.get("tags", [])
    assert isinstance(tags, list) and tags, "标签应为非空列表"  # 标签列表基本校验
