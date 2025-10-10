"""调度队列集成测试，验证 Worker 拉取执行流程。"""  # 中文说明

from __future__ import annotations  # 启用未来注解语法

from pathlib import Path  # 路径处理

import httpx  # HTTP 客户端
import pytest  # 测试框架

from app.dashboard.server import app as dashboard_app  # 引入 FastAPI 应用
from app.dispatch.store import dispatch_session_scope  # 分发库会话
from app.db import migrate_sched  # 引入调度库模块以便重绑 Session
from app.db.migrate_sched import run_migrations, sched_session_scope, get_sched_engine  # 调度库工具
from sqlalchemy.orm import sessionmaker  # Session 工厂
from app.db.models_sched import JobRun, Profile, TaskQueue  # ORM 模型
from app.profiles.loader import sync_profiles  # Profile 同步
from app.scheduler.service import run_profile  # 调度执行函数
from app.worker.agent import DispatchWorker  # Worker 实现
from config.settings import settings  # 全局配置


@pytest.mark.integration  # 标记为集成测试
@pytest.mark.asyncio  # 使用 asyncio 运行
async def test_dispatch_worker_flow(tmp_path: Path, monkeypatch, temp_settings):  # 定义测试函数
    """验证 Scheduler 入队后，Worker 能够拉取并完成任务。"""  # 函数中文说明

    monkeypatch.setattr(settings, "sched_db_url", f"sqlite:///{tmp_path/'sched.db'}")  # 重定向调度数据库
    monkeypatch.setattr(settings, "profiles_dir", str(tmp_path / "profiles"))  # 使用临时 Profile 目录
    monkeypatch.setattr(settings, "worker_enable", True)  # 确保启用 Worker 模式
    settings.worker_auth_token = "test-token"  # 强制设置 Worker Token
    assert settings.worker_auth_token == "test-token"  # 验证已注入 Worker Token
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)  # 创建 Profile 目录
    profile_yaml = tmp_path / "profiles" / "queue_profile.yml"  # 定义 YAML 路径
    profile_yaml.write_text(  # 写入带 dispatch_mode 的配置
        """
name: queue_profile
enabled: true
dispatch_mode: queue
generation:
  articles_per_day: 1
  target_words: 500
  llm_preset: demo
  dedup:
    check_title: true
    check_role_work_pair: true
    hamming_threshold: 0.5
delivery:
  platforms:
    - wechat_mp
    - zhihu
  window:
    start: "08:00"
    end: "09:00"
""".strip(),
        encoding="utf-8",
    )
    engine = get_sched_engine()  # 根据新配置创建引擎
    monkeypatch.setattr(migrate_sched, "SessionSched", sessionmaker(bind=engine))  # 重新绑定调度 Session
    run_migrations()  # 初始化调度数据库
    sync_profiles()  # 同步 Profile 到数据库
    with sched_session_scope() as session:  # 查询 Profile 信息
        profile = session.query(Profile).filter(Profile.name == "queue_profile").one()  # 获取记录
        profile_id = profile.id  # 记录 ID
    run_profile(profile_id)  # 触发调度，预期入队
    with dispatch_session_scope() as session:  # 检查队列状态
        task = session.query(TaskQueue).one()  # 获取单条任务
        assert task.status == "pending"  # 初始状态为待处理
    await dashboard_app.router.startup()  # 启动 FastAPI 生命周期
    try:
        transport = httpx.ASGITransport(app=dashboard_app)  # 使用显式 ASGI 传输
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:  # 创建 ASGI 客户端
            probe = await client.post(  # 手动探测心跳接口
                "/api/dispatch/heartbeat",
                json={"agent_name": "test-agent", "meta": {}},
                headers={"Authorization": "Bearer test-token"},
            )
            assert probe.status_code == 200, probe.text  # 确认心跳接口可用
            worker = DispatchWorker("test-agent", concurrency=1, poll_interval=0.1, server="http://testserver")  # 实例化 Worker
            await worker.run(max_loops=5, client=client)  # 执行有限轮次直至任务完成
    finally:
        await dashboard_app.router.shutdown()  # 确保关闭 FastAPI 生命周期
    with dispatch_session_scope() as session:  # 再次查询队列
        task = session.query(TaskQueue).one()  # 获取任务
        assert task.status == "done"  # 状态应为完成
    with sched_session_scope() as session:  # 校验 JobRun
        job = session.query(JobRun).order_by(JobRun.id.desc()).first()  # 获取最新记录
        assert job is not None  # 确认存在记录
        assert job.status == "success"  # JobRun 状态为成功
        assert job.delivered_success >= 0  # 成功数量为非负
