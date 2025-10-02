"""基础单元测试示例。

包含工具函数、配置解析与去重逻辑的最小验证。
"""

from __future__ import annotations

import importlib  # 用于重新加载配置模块
import json  # 读取角色库 JSON 数据
from typing import Dict  # 为类型标注提供支持

import pytest  # 断言异常

_sqlalchemy = pytest.importorskip("sqlalchemy")  # 若未安装 SQLAlchemy 则跳过测试
from sqlalchemy import create_engine  # 构造内存数据库
from sqlalchemy.orm import sessionmaker  # 构建 Session 工厂

from app.utils.helpers import chunk_items, utc_now_str  # 导入待测试的工具函数
from app.db import models  # 引入 ORM 模型以初始化内存数据库
from app.generator import character_selector  # 引入角色选择工具以验证接口
from config.settings import BASE_DIR  # 提供仓库根目录


def test_chunk_items() -> None:
    """验证 chunk_items 函数能够按预期分组。"""

    data = ["a", "b", "c", "d"]  # 准备测试数据
    result = chunk_items(data, size=2)  # 调用函数进行分组
    assert result == [["a", "b"], ["c", "d"]]  # 断言输出符合期望


def test_chunk_items_invalid_size() -> None:
    """验证非法分组大小会抛出异常。"""

    with pytest.raises(ValueError):  # 预期抛出 ValueError
        chunk_items(["a"], size=0)  # 传入非法 size


def test_utc_now_str_format() -> None:
    """确保 utc_now_str 返回 ISO 格式字符串。"""

    timestamp = utc_now_str()  # 获取当前时间字符串
    assert "T" in timestamp  # ISO8601 中必须包含日期与时间分隔符


def test_settings_timezone(monkeypatch) -> None:
    """验证 TIMEZONE 环境变量能正确覆盖默认值。"""

    monkeypatch.setenv("TIMEZONE", "Asia/Tokyo")  # 设置环境变量
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")  # 避免创建本地文件
    settings_module = importlib.import_module("config.settings")  # 导入配置模块
    importlib.reload(settings_module)  # 重新加载以应用新的环境变量
    try:
        assert settings_module.settings.timezone == "Asia/Tokyo"  # 断言生效
    finally:
        importlib.reload(settings_module)  # 恢复默认状态，避免影响其他测试
        monkeypatch.delenv("TIMEZONE", raising=False)  # 清理环境变量
        monkeypatch.delenv("DATABASE_URL", raising=False)  # 清理数据库配置


def test_deduplicator_keyword_and_title(monkeypatch) -> None:
    """验证去重逻辑能识别标题与关键词重复。"""

    engine = create_engine("sqlite:///:memory:", future=True)  # 创建内存数据库
    models.Base.metadata.create_all(engine)  # 初始化表结构
    session_cls = sessionmaker(bind=engine)  # 构造 Session 工厂

    from app.dedup import deduplicator as dedup_module  # 延迟导入以便 monkeypatch

    monkeypatch.setattr(dedup_module, "SessionLocal", session_cls)  # 替换为内存 Session
    dedup_service = dedup_module.ArticleDeduplicator()  # 使用新的 Session 工厂实例化

    with session_cls() as session:  # 手动写入一篇历史文章
        article = models.Article(title="重复标题", content="正文")  # 构造文章对象
        session.add(article)  # 加入 session
        session.flush()  # 刷新以获得文章 ID
        session.add(models.Keyword(article_id=article.id, keyword="AI"))  # 添加关键词
        session.commit()  # 提交事务

    duplicate_payload: Dict[str, str] = {  # 构造重复文章数据
        "title": "重复标题",
        "content": "正文",
        "keywords": ["AI"],
    }
    fresh_payload: Dict[str, str] = {  # 构造新文章数据
        "title": "全新主题",
        "content": "内容",
        "keywords": ["新关键词"],
    }

    assert not dedup_service.is_unique(duplicate_payload)  # 标题重复应被拒绝
    assert dedup_service.is_unique(fresh_payload)  # 新标题与新关键词应通过


def test_characters_json_is_valid() -> None:
    """验证角色库文件能被正常解析并包含必要字段。"""

    path = BASE_DIR / "app" / "generator" / "characters.json"  # 拼接角色库路径
    data = json.loads(path.read_text(encoding="utf-8"))  # 读取并解析 JSON
    assert isinstance(data, list)  # 顶层结构必须是列表
    for entry in data:  # 遍历每个角色条目
        assert isinstance(entry, dict)  # 条目必须是对象
        assert set(entry.keys()) == {"name", "work", "traits"}  # 验证字段完整
        assert isinstance(entry["name"], str) and entry["name"].strip()  # name 非空
        assert isinstance(entry["work"], str) and entry["work"].strip()  # work 非空
        assert isinstance(entry["traits"], list) and entry["traits"]  # traits 非空列表
        assert all(isinstance(trait, str) and trait.strip() for trait in entry["traits"])  # 特质均为非空字符串


def test_character_name_work_unique() -> None:
    """确保角色库中的 (name, work) 组合全局唯一。"""

    path = BASE_DIR / "app" / "generator" / "characters.json"  # 角色库路径
    data = json.loads(path.read_text(encoding="utf-8"))  # 解析 JSON
    seen: set[tuple[str, str]] = set()  # 记录已出现的组合
    for entry in data:  # 遍历角色
        key = (entry["name"], entry["work"])  # 组合键
        assert key not in seen  # 不允许重复
        seen.add(key)  # 收录组合


def test_get_random_character_structure() -> None:
    """验证随机角色选择函数返回结构与数据类型。"""

    character = character_selector.get_random_character()  # 获取随机角色
    assert character["name"]  # 角色名非空
    assert character["work"]  # 作品名非空
    assert isinstance(character["traits"], list) and character["traits"]  # 特质为非空列表
    assert all(isinstance(trait, str) and trait for trait in character["traits"])  # 特质项类型正确
