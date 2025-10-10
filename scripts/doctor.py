"""系统自检脚本：检查配置、目录、Profile 与调度状态。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from pathlib import Path  # 处理路径

from config.settings import settings, print_config  # 配置对象与打印函数
from app.db.migrate import init_database  # 主业务数据库迁移
from app.db.migrate_sched import run_migrations, sched_session_scope  # 调度数据库工具
from app.db.models_sched import MetricEvent, Schedule  # 调度 ORM 模型
from app.profiles.loader import sync_profiles, list_profiles  # Profile 工具
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志

STATUS_OK = "✅"  # 成功图标
STATUS_WARN = "⚠️"  # 警告图标
STATUS_FAIL = "❌"  # 失败图标


def check_secret() -> tuple[str, str]:  # 检查 JWT 密钥
    """确保 Dashboard JWT 密钥已配置。"""  # 中文说明

    if settings.dashboard_jwt_secret:
        return STATUS_OK, "Dashboard JWT 密钥已配置"  # 成功信息
    return STATUS_FAIL, "缺少 DASHBOARD_JWT_SECRET"  # 失败信息


def check_directories() -> list[tuple[str, str]]:  # 检查目录
    """检查关键目录的存在与可写性。"""  # 中文说明

    results: list[tuple[str, str]] = []  # 结果列表
    for label, path in [
        ("Profiles 目录", Path(settings.profiles_dir)),
        ("Plugins 目录", Path(settings.plugins_dir)),
        ("Sessions 目录", Path(settings.session_dir)),
    ]:  # 遍历目录
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".doctor.probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            results.append((STATUS_OK, f"{label}: {path} 可写"))
        except Exception as exc:  # noqa: BLE001
            results.append((STATUS_FAIL, f"{label}: {path} 不可写 -> {exc}"))
    return results


def check_profiles() -> list[tuple[str, str]]:  # 检查 Profile
    """同步并列出 Profile 状态。"""  # 中文说明

    run_migrations()  # 确保调度数据库存在
    profiles = sync_profiles()  # 同步 YAML
    if not profiles:
        return [(STATUS_WARN, "未找到任何 Profile YAML，请检查 profiles 目录")]
    rows = list_profiles()
    return [(STATUS_OK, f"Profile {row['name']} 已加载，启用={row['enabled']}") for row in rows]


def check_scheduler() -> list[tuple[str, str]]:  # 检查调度表
    """验证调度表是否存在记录。"""  # 中文说明

    items: list[tuple[str, str]] = []
    with sched_session_scope() as session:
        schedules = session.query(Schedule).all()
        if schedules:
            for sch in schedules:
                items.append((STATUS_OK, f"Schedule#{sch.id} Profile={sch.profile_id} Cron={sch.cron_expr} Paused={sch.is_paused}"))
        else:
            items.append((STATUS_WARN, "暂无调度记录，可运行 scripts/schedule_profile.py 创建"))
        metric_count = session.query(MetricEvent).count()
        items.append((STATUS_OK, f"指标事件累计 {metric_count} 条"))
    return items


def main() -> None:  # 主函数
    """执行全部自检并打印结果。"""  # 中文说明

    print_config(mask_secrets=True)  # 输出配置
    init_database()  # 确保主数据库存在
    run_migrations()  # 确保调度数据库存在
    status, message = check_secret()
    print(status, message)
    for status_item, message_item in check_directories():
        print(status_item, message_item)
    for status_item, message_item in check_profiles():
        print(status_item, message_item)
    for status_item, message_item in check_scheduler():
        print(status_item, message_item)
    print(STATUS_OK, "自检完成")


if __name__ == "__main__":  # 脚本入口
    main()  # 调用主函数
