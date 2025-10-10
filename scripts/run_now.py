"""立即执行指定 Profile 的调度任务。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数

from app.db.migrate_sched import run_migrations  # 调度数据库迁移
from app.profiles.loader import sync_profiles  # Profile 同步
from app.db.migrate_sched import sched_session_scope  # Session 上下文
from app.db.models_sched import Profile  # Profile 模型
from app.scheduler.service import run_profile  # 调度执行函数


def parse_args() -> argparse.Namespace:  # 参数解析
    """解析命令行参数，获取 Profile 名称。"""  # 中文说明

    parser = argparse.ArgumentParser(description="立即执行 Profile")  # 初始化解析器
    parser.add_argument("--profile", required=True, help="Profile 名称")  # Profile 参数
    return parser.parse_args()  # 返回解析结果


def main() -> None:  # 主函数
    """同步 Profile 并执行调度任务。"""  # 中文说明

    args = parse_args()  # 解析参数
    run_migrations()  # 确保调度数据库存在
    sync_profiles()  # 同步 YAML
    with sched_session_scope() as session:  # 打开 Session
        profile = session.query(Profile).filter(Profile.name == args.profile).one_or_none()  # 查询 Profile
        if profile is None:  # 未找到
            raise SystemExit(f"未找到 Profile {args.profile}")  # 终止
        run_profile(profile.id)  # 直接执行


if __name__ == "__main__":  # 脚本入口
    main()  # 调用主函数
