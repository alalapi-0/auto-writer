"""基础单元测试覆盖 orchestrator 关键路径。"""

from __future__ import annotations

import importlib  # 用于重新加载配置模块
import json  # 解析 JSON 文件
from datetime import date, datetime, timedelta  # 构造时间数据
from pathlib import Path  # 处理路径
import pytest  # 断言与跳过
from sqlalchemy import create_engine  # 构造内存数据库
from sqlalchemy.orm import sessionmaker  # 构建 Session 工厂

from app.db import models  # 导入 ORM 模型

from app.orchestrator import orchestrator, parsers, vps_job_packager  # 引入 orchestrator 组件
from app.utils.helpers import chunk_items, utc_now_str  # 测试工具函数
from config.settings import BASE_DIR, settings  # 仓库根路径与配置


def test_chunk_items() -> None:
    """验证 chunk_items 函数能够按预期分组。"""

    data = ["a", "b", "c", "d"]
    result = chunk_items(data, size=2)
    assert result == [["a", "b"], ["c", "d"]]


def test_chunk_items_invalid_size() -> None:
    """验证非法分组大小会抛出异常。"""

    with pytest.raises(ValueError):
        chunk_items(["a"], size=0)


def test_utc_now_str_format() -> None:
    """确保 utc_now_str 返回 ISO 格式字符串。"""

    timestamp = utc_now_str()
    assert "T" in timestamp


def test_settings_timezone(monkeypatch) -> None:
    """验证 TIMEZONE 环境变量能正确覆盖默认值。"""

    monkeypatch.setenv("TIMEZONE", "Asia/Tokyo")
    monkeypatch.setenv("DB_URL", "sqlite:///:memory:")
    settings_module = importlib.import_module("config.settings")
    importlib.reload(settings_module)
    try:
        assert settings_module.settings.orchestrator.timezone == "Asia/Tokyo"
    finally:
        importlib.reload(settings_module)
        monkeypatch.delenv("TIMEZONE", raising=False)
        monkeypatch.delenv("DB_URL", raising=False)


def _build_session():
    """构造内存数据库 Session。"""

    engine = create_engine("sqlite:///:memory:", future=True)
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_planner_prefers_unused_keywords() -> None:
    """Planner 应优先选择未使用或冷却窗外的关键词。"""

    session_cls = _build_session()
    with session_cls() as session:
        session.add(models.Character(name="夏洛克", work="神探夏洛克", traits="推理,冷静"))
        session.add(models.Keyword(keyword="新鲜关键词", last_used_at=None))
        session.add(
            models.Keyword(
                keyword="旧关键词",
                last_used_at=datetime.utcnow() - timedelta(days=120),
            )
        )
        session.commit()
        plan = orchestrator.plan_topics(session, target_count=1, cooldown_days=30)
    assert plan and plan[0]["keyword"] == "新鲜关键词"


def test_preflight_dedup_removes_same_day_duplicates() -> None:
    """Preflight 去重应剔除当日重复的 (角色, 作品, 关键词)。"""

    session_cls = _build_session()
    today = date(2025, 10, 2)
    with session_cls() as session:
        session.add(models.UsedPair(
            character_name="张三",
            work="示例剧集",
            keyword="心理对抗",
            run_id="run-1",
            used_on=today,
        ))
        session.commit()
        topics = [
            {"character_name": "张三", "work": "示例剧集", "keyword": "心理对抗"},
            {"character_name": "李四", "work": "另一个剧", "keyword": "成长曲线"},
        ]
        deduped = orchestrator.preflight_scan(session, topics, today)
    assert deduped == [topics[1]]


def test_job_packager_output_matches_schema(tmp_path: Path) -> None:
    """vps_job_packager 生成的 job.json 必须符合 JSON Schema。"""

    jsonschema = pytest.importorskip("jsonschema")  # 若缺少依赖则跳过此测试
    payload_topics = [
        {"character_name": "夏洛克", "work": "神探夏洛克", "keyword": "行为主义"}
    ]
    job_path, temp_dir, env_path = vps_job_packager.pack_job_and_env(
        settings,
        run_id="test-run",
        run_date="2025-10-02",
        planned_articles=len(payload_topics),
        topics=payload_topics,
        template_options={"style": "psychology_analysis"},
        delivery_targets={"wordpress": True},
        output_dir=tmp_path,
    )
    schema = json.loads((BASE_DIR / "jobs" / "job.schema.json").read_text(encoding="utf-8"))
    job_data = json.loads(job_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=job_data, schema=schema)
    assert env_path.exists()
    assert temp_dir.exists()


def test_parser_persist_and_enrich() -> None:
    """解析 result.json 后应正确落表并触发补词。"""

    session_cls = _build_session()
    run_date = date(2025, 10, 2)
    with session_cls() as session:
        run = models.Run(run_id="run-x", run_date=run_date, planned_articles=3)
        session.add(run)
        session.add(models.Keyword(keyword="关键词A"))
        session.add(models.Keyword(keyword="关键词B"))
        session.add(models.Keyword(keyword="关键词C"))
        session.commit()
        result_payload = {
            "run_id": "run-x",
            "success": True,
            "articles": [
                {
                    "character_name": "角色1",
                    "work": "作品1",
                    "keyword": "关键词A",
                    "status": "draft_pushed",
                    "content": "...",
                    "platform_results": [{"platform": "wordpress", "ok": True, "id_or_url": "wp-1"}],
                },
                {
                    "character_name": "角色2",
                    "work": "作品2",
                    "keyword": "关键词B",
                    "status": "draft_pushed",
                    "content": "...",
                    "platform_results": [],
                },
                {
                    "character_name": "角色3",
                    "work": "作品3",
                    "keyword": "关键词C",
                    "status": "draft_pushed",
                    "content": "...",
                    "platform_results": [],
                },
            ],
            "errors": [],
        }
        consumed = parsers.persist_results(session, run, result_payload)
        assert session.query(models.UsedPair).count() == 3
        created = parsers.perform_postrun_enrich(session, run, consumed, group_size=3)
        assert len(created) == 3
        assert run.keywords_consumed == 3
        assert run.keywords_added == 3
