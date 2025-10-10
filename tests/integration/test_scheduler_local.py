"""本地调度集成测试，验证 run_profile 基础链路。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import os  # 操作目录
from pathlib import Path  # 路径处理

from app.scheduler.service import run_profile  # 调度执行函数
from app.db import migrate_sched  # 调度数据库模块
from app.db.migrate_sched import run_migrations, sched_session_scope, get_sched_engine  # 调度数据库工具
from app.db.models_sched import JobRun, MetricEvent, Profile  # ORM 模型
from app.profiles.loader import sync_profiles  # Profile 同步
from app.plugins import loader  # 插件管理器
from config.settings import settings  # 配置对象


def test_run_profile_local(tmp_path, monkeypatch):  # 定义测试函数
    """构建临时 Profile 并执行 run_profile，断言运行记录与指标生成。"""  # 中文说明

    monkeypatch.setattr(settings, "sched_db_url", f"sqlite:///{tmp_path/'sched.db'}")  # 重定向调度数据库
    monkeypatch.setattr(settings, "profiles_dir", str(tmp_path / "profiles"))  # 使用临时 Profile 目录
    monkeypatch.setattr(settings, "plugins_dir", str(Path(__file__).resolve().parents[2] / "plugins"))  # 指向仓库插件目录
    monkeypatch.setattr(settings, "outbox_dir", str(tmp_path / "outbox"))  # 设置 outbox 目录
    monkeypatch.setattr(loader, "_manager", None)  # 重置插件管理器缓存
    engine = get_sched_engine()  # 使用新配置创建引擎
    from sqlalchemy.orm import sessionmaker  # 延迟导入 sessionmaker

    monkeypatch.setattr(migrate_sched, "SessionSched", sessionmaker(bind=engine))  # 更新 Session 工厂
    (tmp_path / "outbox").mkdir(parents=True, exist_ok=True)  # 创建 outbox
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)  # 创建 profiles 目录
    profile_yaml = tmp_path / "profiles" / "test.yml"  # Profile 文件路径
    profile_yaml.write_text(
        """
name: test_profile
enabled: true
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
  window:
    start: "08:00"
    end: "09:00"
playwright:
  headless: true
  slowmo_ms: 0
""".strip(),
        encoding="utf-8",
    )  # 写入示例 YAML
    run_migrations()  # 初始化调度数据库
    sync_profiles()  # 同步 Profile
    with sched_session_scope() as session:  # 查询 Profile ID
        profile = session.query(Profile).filter(Profile.name == "test_profile").one()
        profile_id = profile.id
    cwd_before = Path.cwd()  # 记录当前目录
    os.chdir(tmp_path)  # 切换到临时目录，便于插件输出
    try:
        run_profile(profile_id)  # 执行调度
    finally:
        os.chdir(cwd_before)  # 还原工作目录
    with sched_session_scope() as session:  # 检查运行结果
        job = session.query(JobRun).order_by(JobRun.id.desc()).first()
        assert job is not None  # 断言存在运行记录
        assert job.status in {"success", "partial", "failed"}  # 状态在预期集合内
        metrics = session.query(MetricEvent).all()
        assert metrics, "应至少写入一条指标事件"  # 指标非空
    video_stub_dir = tmp_path / "outbox" / "video_todo"  # 插件输出目录
    assert video_stub_dir.exists(), "视频插件应创建输出目录"  # 断言目录存在
