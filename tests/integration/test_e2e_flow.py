# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""端到端集成测试，覆盖生成、投递、重试与报表流程。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import json  # 解析报表
import sys  # 修改命令行参数
from datetime import datetime, timedelta, timezone  # 处理时间

import pytest  # 引入测试框架
from sqlalchemy import text  # 执行原生 SQL

import scripts.export_report as export_report_script  # 导入报表脚本模块
import scripts.retry_due as retry_due_script  # 导入重试脚本模块
from app.delivery.dispatcher import deliver_article_to_all  # 引入投递调度器
from app.db.migrate import SessionLocal  # 获取 Session 工厂
from config.settings import settings  # 使用全局配置


@pytest.mark.integration
def test_e2e_flow(temp_settings, monkeypatch) -> None:  # 集成测试入口
    """验证核心链路：主题准备、投递、失败重试与报表导出。"""  # 测试说明

    env_paths = temp_settings  # 获取夹具返回的路径字典
    original_argv = list(sys.argv)  # 记录原始命令行参数

    topics = [  # 构造三条未使用主题
        {
            "keyword": "自信训练",
            "definition": "探讨自信构建技巧",
            "character": "艾丽丝",
            "show": "心理课堂",
        },
        {
            "keyword": "正念冥想",
            "definition": "结合正念的放松方法",
            "character": "拓也",
            "show": "东方疗愈",
        },
        {
            "keyword": "情绪疗愈",
            "definition": "处理情绪创伤的流程",
            "character": "莉亚",
            "show": "治愈之森",
        },
    ]
    with SessionLocal() as session:  # 打开数据库会话
        with session.begin():  # 开启事务写入主题与关键词
            for item in topics:  # 遍历主题
                session.execute(  # 插入主题记录
                    text(
                        """
                        INSERT INTO psychology_themes (
                            psychology_keyword,
                            psychology_definition,
                            character_name,
                            show_name,
                            used
                        ) VALUES (:keyword, :definition, :character, :show, 0)
                        """
                    ),
                    {
                        "keyword": item["keyword"],
                        "definition": item["definition"],
                        "character": item["character"],
                        "show": item["show"],
                    },
                )
                session.execute(  # 插入关键词记录
                    text(
                        """
                        INSERT INTO keywords (keyword, category, usage_count, is_active, created_at)
                        VALUES (:keyword, 'integration', 0, 1, :created_at)
                    """
                ),
                    {"keyword": item["keyword"], "created_at": datetime.now(timezone.utc).isoformat()},
                )

    article_title = "集成测试文章"  # 定义文章标题
    created_at = datetime.now(timezone.utc).isoformat()  # 生成创建时间
    with SessionLocal() as session:  # 打开会话写入文章
        with session.begin():  # 开启事务
            session.execute(  # 插入文章草稿
                text(
                    """
                    INSERT INTO articles (
                        character_name,
                        work,
                        keyword,
                        title,
                        content,
                        created_at,
                        status
                    ) VALUES (:character, :work, :keyword, :title, :content, :created_at, 'draft')
                    """
                ),
                {
                    "character": topics[0]["character"],
                    "work": topics[0]["show"],
                    "keyword": topics[0]["keyword"],
                    "title": article_title,
                    "content": "测试正文",
                    "created_at": created_at,
                },
            )
            article_id = session.execute(  # 获取插入的文章 ID
                text("SELECT id FROM articles ORDER BY id DESC LIMIT 1")
            ).scalar()

    assert article_id is not None  # 断言文章成功写入

    with SessionLocal() as session:  # 打开新会话进行投递
        delivery_results = deliver_article_to_all(session, settings, article_id=article_id)  # 调用投递器

    assert set(delivery_results.keys()) == {"wechat_mp", "zhihu"}  # 校验覆盖两个平台
    for platform, result in delivery_results.items():  # 遍历结果
        assert result.status in {"prepared", "success"}  # 确认状态为成功或已准备

    today_str = datetime.now().strftime("%Y%m%d")  # 获取日期目录
    for platform in ("wechat_mp", "zhihu"):  # 检查 outbox 目录
        draft_path = env_paths["outbox"] / platform / today_str / article_title / "draft.md"  # 构造文件路径
        assert draft_path.exists()  # 确认草稿文件生成

    with SessionLocal() as session:  # 打开会话检查 platform_logs
        log_rows = session.execute(
            text("SELECT platform, status FROM platform_logs WHERE article_id = :aid"),
            {"aid": article_id},
        ).mappings().all()
    assert len(log_rows) == 2  # 两个平台均应写入日志
    assert {row["status"] for row in log_rows} <= {"prepared", "success"}  # 状态需正常

    run_id = "run-e2e"  # 定义运行 ID
    run_now = datetime.now(timezone.utc)  # 获取当前时间
    with SessionLocal() as session:  # 打开会话写入运行记录
        with session.begin():  # 开启事务
            session.execute(  # 插入 runs 记录
                text(
                    """
                    INSERT INTO runs (
                        run_id,
                        run_date,
                        planned_articles,
                        status,
                        keywords_consumed,
                        keywords_added,
                        created_at,
                        updated_at
                    ) VALUES (
                        :run_id,
                        :run_date,
                        :planned,
                        'generating',
                        0,
                        0,
                        :created,
                        :updated
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "run_date": run_now.date(),
                    "planned": 1,
                    "created": run_now,
                    "updated": run_now,
                },
            )
            for status in ("prepared", "delivering", "success"):  # 模拟状态迁移
                session.execute(
                    text("UPDATE runs SET status = :status, updated_at = :updated WHERE run_id = :run_id"),
                    {"status": status, "updated": datetime.now(timezone.utc), "run_id": run_id},
                )
    with SessionLocal() as session:  # 验证最终状态
        final_status = session.execute(
            text("SELECT status FROM runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
    assert final_status == "success"  # 确认状态机完成

    failing_title = "需重试文章"  # 定义失败文章标题
    with SessionLocal() as session:  # 写入第二篇文章
        with session.begin():  # 开启事务
            session.execute(
                text(
                    """
                    INSERT INTO articles (character_name, work, keyword, title, content, created_at, status)
                    VALUES (:character, :work, :keyword, :title, :content, :created_at, 'draft')
                    """
                ),
                {
                    "character": topics[1]["character"],
                    "work": topics[1]["show"],
                    "keyword": topics[1]["keyword"],
                    "title": failing_title,
                    "content": "失败重试正文",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            failing_article_id = session.execute(
                text("SELECT id FROM articles ORDER BY id DESC LIMIT 1")
            ).scalar()

    assert failing_article_id is not None  # 确认文章写入

    import app.delivery.wechat_mp_adapter as wechat_adapter  # 导入公众号适配器

    original_deliver = wechat_adapter.deliver  # 记录原始实现
    call_counter = {"count": 0}  # 记录调用次数

    def _failing_deliver(article: dict, current_settings) -> None:  # 定义失败版本投递
        call_counter["count"] += 1  # 自增计数
        raise RuntimeError("mock failure")  # 抛出异常

    monkeypatch.setattr(wechat_adapter, "deliver", _failing_deliver)  # 注入失败适配器

    with SessionLocal() as session:  # 打开会话执行失败投递
        failure_results = deliver_article_to_all(session, settings, article_id=failing_article_id)  # 调用投递

    assert call_counter["count"] == 1  # 确认适配器被调用
    assert failure_results["wechat_mp"].status == "failed"  # 微信状态失败
    assert failure_results["zhihu"].status in {"prepared", "success"}  # 知乎仍成功

    with SessionLocal() as session:  # 查询失败日志
        fail_log = session.execute(
            text(
                """
                SELECT status, attempt_count, next_retry_at
                FROM platform_logs
                WHERE article_id = :aid AND platform = 'wechat_mp'
                """
            ),
            {"aid": failing_article_id},
        ).mappings().first()
    assert fail_log is not None  # 确认日志存在
    assert fail_log["status"] == "failed"  # 状态为失败
    assert fail_log["attempt_count"] == 1  # 首次失败记录一次
    assert fail_log["next_retry_at"] is not None  # 设置了下一次重试时间
    next_retry_time = datetime.fromisoformat(str(fail_log["next_retry_at"]))  # 解析重试时间
    assert next_retry_time > datetime.now(timezone.utc) - timedelta(seconds=1)  # 确认重试时间晚于当前

    wechat_adapter.deliver = original_deliver  # 手动恢复适配器实现

    with SessionLocal() as session:  # 将重试时间调整到过去
        with session.begin():  # 开启事务
                session.execute(
                    text(
                        "UPDATE platform_logs SET next_retry_at = :due WHERE article_id = :aid AND platform = 'wechat_mp'"
                    ),
                    {"due": "1970-01-01 00:00:00", "aid": failing_article_id},
                )

    monkeypatch.setattr(sys, "argv", ["retry_due.py", "--limit", "5"])  # 设置命令行参数
    retry_due_script.main()  # 运行重试脚本

    with SessionLocal() as session:  # 查询重试后的日志
        retry_log = session.execute(
            text(
                """
                SELECT status, attempt_count, next_retry_at
                FROM platform_logs
                WHERE article_id = :aid AND platform = 'wechat_mp'
                """
            ),
            {"aid": failing_article_id},
        ).mappings().first()
    assert retry_log is not None  # 日志必须存在
    assert retry_log["attempt_count"] >= 2  # 尝试次数递增
    assert retry_log["status"] in {"prepared", "success"}  # 状态应恢复
    assert retry_log["next_retry_at"] is None  # 成功后清除重试时间

    monkeypatch.setattr(sys, "argv", ["export_report.py", "--window", "7"])  # 配置报表参数
    export_report_script.main()  # 执行报表导出

    export_json_files = list(env_paths["exports"].glob("report_*.json"))  # 搜索 JSON 报表
    export_csv_files = list(env_paths["exports"].glob("report_*.csv"))  # 搜索 CSV 报表
    assert export_json_files, "JSON 报表应生成"  # JSON 必须存在
    assert export_csv_files, "CSV 报表应生成"  # CSV 必须存在

    report_data = json.loads(export_json_files[0].read_text(encoding="utf-8"))  # 读取 JSON 内容
    assert report_data["metrics"]["article_counts"] != {}  # 文章统计非空
    assert report_data["metrics"]["platform"], "平台指标应包含数据"  # 平台指标存在
    assert report_data["metrics"]["top_entities"]["keywords"] is not None  # 关键词列表存在
    sys.argv = original_argv  # 恢复命令行参数
