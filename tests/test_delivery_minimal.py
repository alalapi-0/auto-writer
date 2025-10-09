"""验证最小投递链路的端到端行为。"""  # 模块中文说明
from __future__ import annotations  # 启用未来注解语法

from datetime import datetime, timezone  # 处理时间
from types import SimpleNamespace  # 构造临时配置对象

import pytest  # 测试框架
from sqlalchemy import create_engine, text  # 创建引擎与执行 SQL
from sqlalchemy.orm import sessionmaker  # 构造会话工厂

from app.delivery.dispatcher import deliver_article_to_all  # 被测分发器
from app.delivery.types import DeliveryResult  # 引入返回类型


def _build_session_factory():
    """创建内存数据库并初始化基础表。"""  # 辅助函数中文文档

    engine = create_engine("sqlite:///:memory:", future=True)  # 创建内存数据库
    with engine.begin() as conn:  # 打开事务
        conn.execute(
            text(
                """
                CREATE TABLE articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    content TEXT,
                    role_slug TEXT,
                    work_slug TEXT,
                    psych_keyword TEXT,
                    lang TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )  # 创建文章表
        conn.execute(
            text(
                """
                CREATE TABLE platform_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    target_id TEXT,
                    status TEXT,
                    ok INTEGER DEFAULT 0,
                    id_or_url TEXT,
                    error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_retry_at TIMESTAMP,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )  # 创建平台日志表
    return sessionmaker(bind=engine, future=True)  # 返回会话工厂


def test_delivery_minimal_success(tmp_path):
    """成功分发时应生成 outbox 制品并写入日志。"""  # 测试用例中文说明

    session_factory = _build_session_factory()  # 初始化会话工厂
    with session_factory() as session:  # 打开会话
        session.execute(  # 插入测试文章
            text(
                """
                INSERT INTO articles (title, content, role_slug, work_slug, psych_keyword, lang)
                VALUES (:title, :content, :role, :work, :keyword, :lang)
                """
            ),
            {
                "title": "测试公众号文章",
                "content": "第一段\n第二段",
                "role": "role-x",
                "work": "work-y",
                "keyword": "keyword-z",
                "lang": "zh",
            },
        )
        session.commit()  # 提交写入
        article_id = session.execute(text("SELECT id FROM articles LIMIT 1")).scalar_one()  # 获取文章 ID
        stub_settings = SimpleNamespace(  # 构造临时配置
            delivery_enabled_platforms=["wechat_mp", "zhihu"],
            outbox_dir=str(tmp_path),
            retry_base_seconds=1,
            retry_max_attempts=3,
        )
        results = deliver_article_to_all(session, stub_settings, article_id)  # 执行分发
        assert results["wechat_mp"].status == "prepared"  # 公众号状态应为 prepared
        assert results["zhihu"].status == "prepared"  # 知乎状态应为 prepared
        count = session.execute(text("SELECT COUNT(*) FROM platform_logs")).scalar_one()  # 查询日志数量
        assert count == 2  # 应写入两条日志
        statuses = session.execute(  # 读取各平台状态
            text("SELECT platform, status FROM platform_logs ORDER BY platform")
        ).fetchall()
        assert {row[1] for row in statuses} == {"prepared"}  # 状态均为 prepared
        day = datetime.now(timezone.utc).strftime("%Y%m%d")  # 计算当天目录（使用 UTC 防止跨时区）
        wx_dir = tmp_path / "wechat_mp" / day / "测试公众号文章"  # 构造公众号目录
        zh_dir = tmp_path / "zhihu" / day / "测试公众号文章"  # 构造知乎目录
        assert (wx_dir / "draft.md").exists()  # 确认 Markdown 输出
        assert (wx_dir / "draft.html").exists()  # 确认 HTML 输出
        assert (wx_dir / "meta.json").exists()  # 确认元数据输出
        assert (zh_dir / "draft.md").exists()  # 确认知乎 Markdown 输出
        assert (zh_dir / "meta.json").exists()  # 确认知乎元数据输出


def test_delivery_retry_flow(tmp_path, monkeypatch):
    """失败后应记录重试窗口并在 retry_due 中恢复成功。"""  # 测试用例中文说明

    session_factory = _build_session_factory()  # 创建会话工厂
    with session_factory() as session:  # 打开会话
        session.execute(  # 写入测试文章
            text(
                """
                INSERT INTO articles (title, content, role_slug, work_slug, psych_keyword, lang)
                VALUES ('失败案例', '正文', 'role-x', 'work-y', 'keyword-z', 'zh')
                """
            )
        )
        session.commit()  # 提交写入
        article_id = session.execute(text("SELECT id FROM articles LIMIT 1")).scalar_one()  # 获取文章 ID
        stub_settings = SimpleNamespace(  # 构造临时配置
            delivery_enabled_platforms=["wechat_mp"],
            outbox_dir=str(tmp_path),
            retry_base_seconds=0,
            retry_max_attempts=2,
        )

        def failing_registry(_settings):
            """返回抛出异常的适配器。"""  # 内部函数说明

            def _fail_adapter(article, settings):  # noqa: ARG001
                raise RuntimeError("boom")  # 抛出测试异常

            return {"wechat_mp": _fail_adapter}  # 返回映射

        monkeypatch.setattr("app.delivery.dispatcher.get_registry", failing_registry)  # 替换注册表
        failure_results = deliver_article_to_all(session, stub_settings, article_id)  # 首次分发返回失败
        assert failure_results["wechat_mp"].status == "failed"  # 状态应为 failed
        log_row = session.execute(  # 查询日志
            text(
                """
                SELECT status, attempt_count, next_retry_at, last_error
                FROM platform_logs
                WHERE platform = 'wechat_mp'
                """
            )
        ).mappings().one()
        assert log_row["status"] == "failed"  # 记录状态为 failed
        assert log_row["attempt_count"] == 1  # 尝试次数为 1
        assert log_row["next_retry_at"] is not None  # 已计算下次时间
        assert log_row["last_error"] == "boom"  # 错误信息记录

        def success_registry(_settings):
            """返回立即成功的适配器。"""  # 内部函数说明

            def _ok_adapter(article, settings):  # noqa: ARG001
                return DeliveryResult(  # 构造成功结果
                    platform="wechat_mp",
                    status="prepared",
                    target_id=None,
                    out_dir=str(tmp_path / "wechat_mp"),
                    payload={"files": []},
                    error=None,
                )

            return {"wechat_mp": _ok_adapter}  # 返回成功映射

        monkeypatch.setattr("app.delivery.dispatcher.get_registry", success_registry)  # 切换为成功适配器
        import scripts.retry_due as retry_script  # 延迟导入脚本

        monkeypatch.setattr(retry_script, "SessionLocal", session_factory)  # 注入测试会话
        monkeypatch.setattr(retry_script, "settings", stub_settings)  # 注入测试配置
        retry_script.main()  # 执行重试脚本
        refreshed = session.execute(  # 再次读取日志
            text(
                """
                SELECT status, attempt_count
                FROM platform_logs
                WHERE platform = 'wechat_mp'
                """
            )
        ).mappings().one()
        assert refreshed["status"] == "prepared"  # 状态应更新为 prepared
        assert refreshed["attempt_count"] == 2  # 重试后次数递增
