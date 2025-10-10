"""Profile 调度管理脚本。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数

from app.db.migrate_sched import sched_session_scope, run_migrations  # 调度数据库工具
from app.db.models_sched import Profile, Schedule  # ORM 模型
from app.profiles.loader import sync_profiles  # Profile 同步


def parse_args() -> argparse.Namespace:  # 参数解析
    """定义 CLI 参数用于创建或更新调度。"""  # 中文说明

    parser = argparse.ArgumentParser(description="配置 Profile 调度")  # 初始化解析器
    parser.add_argument("--profile-name", required=True, help="Profile 名称")  # Profile 名称
    parser.add_argument("--cron", help="Cron 表达式，留空仅修改状态")  # Cron 表达式
    parser.add_argument("--pause", action="store_true", help="暂停调度")  # 暂停选项
    parser.add_argument("--resume", action="store_true", help="恢复调度")  # 恢复选项
    return parser.parse_args()  # 返回参数


def ensure_profile(name: str) -> Profile:  # 获取 Profile
    """确保 Profile 存在，若未同步则触发同步流程。"""  # 中文说明

    run_migrations()  # 确保数据库存在
    sync_profiles()  # 同步 YAML
    with sched_session_scope() as session:  # 打开 Session
        profile = session.query(Profile).filter(Profile.name == name).one_or_none()  # 查询 Profile
        if profile is None:  # 未找到
            raise SystemExit(f"未找到 Profile {name}")  # 终止
        return profile  # 返回 Profile


def upsert_schedule(profile: Profile, cron: str | None, pause: bool, resume: bool) -> None:  # 调度写入
    """根据参数创建或更新调度记录。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        schedule = session.query(Schedule).filter(Schedule.profile_id == profile.id).one_or_none()  # 查询调度
        if schedule is None:  # 新建
            schedule = Schedule(profile_id=profile.id, cron_expr=cron or "0 9 * * *")  # 默认 cron
            session.add(schedule)  # 添加记录
        if cron:
            schedule.cron_expr = cron  # 更新 cron
        if pause:
            schedule.is_paused = True  # 设置暂停
        if resume:
            schedule.is_paused = False  # 取消暂停


def main() -> None:  # 主函数
    """解析参数并执行调度更新。"""  # 中文说明

    args = parse_args()  # 解析参数
    profile = ensure_profile(args.profile_name)  # 获取 Profile
    upsert_schedule(profile, args.cron, args.pause, args.resume)  # 更新调度
    print(f"已更新 Profile {profile.name} 调度")  # 输出结果


if __name__ == "__main__":  # 脚本入口
    main()  # 调用主函数
