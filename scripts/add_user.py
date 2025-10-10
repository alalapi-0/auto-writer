"""Dashboard 用户创建脚本。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import getpass  # 安全读取密码

from config.settings import settings  # 引入配置
from app.auth.security import hash_password  # 密码哈希工具
from app.db.migrate_sched import sched_session_scope, run_migrations  # 调度数据库工具
from app.db.models_sched import User  # 用户模型


ROLE_CHOICES = ["admin", "operator", "viewer"]  # 支持的角色列表


def parse_args() -> argparse.Namespace:  # 参数解析函数
    """定义并解析命令行参数。"""  # 中文说明

    parser = argparse.ArgumentParser(description="创建 Dashboard 用户")  # 初始化解析器
    parser.add_argument("--username", required=True, help="登录用户名")  # 用户名参数
    parser.add_argument("--role", choices=ROLE_CHOICES, default="viewer", help="用户角色")  # 角色参数
    parser.add_argument("--init-token", help="管理员初始化令牌，可覆盖环境变量")  # 初始化令牌
    return parser.parse_args()  # 返回解析结果


def ensure_admin_token(role: str, provided: str | None) -> None:  # 校验管理员初始化令牌
    """若创建管理员账号且设置了初始化令牌，则强制校验。"""  # 中文说明

    required = settings.admin_init_token  # 读取配置
    if role != "admin" or not required:  # 非管理员或未设置
        return  # 直接返回
    token = provided or getpass.getpass("请输入管理员初始化令牌: ")  # 获取令牌
    if token != required:  # 校验失败
        raise SystemExit("初始化令牌错误，无法创建管理员账号")  # 终止程序


def prompt_password() -> str:  # 读取密码
    """从终端读取一次性密码并返回哈希值。"""  # 中文说明

    password = getpass.getpass("请输入一次性密码: ")  # 读取密码
    if len(password) < 8:  # 简单长度校验
        raise SystemExit("密码长度至少 8 位")  # 终止
    confirm = getpass.getpass("请再次输入以确认: ")  # 确认密码
    if password != confirm:  # 两次不一致
        raise SystemExit("两次输入不一致")  # 终止
    return hash_password(password)  # 返回哈希


def create_user(username: str, role: str, password_hash: str) -> None:  # 创建用户
    """在数据库中写入用户记录，若存在则更新密码。"""  # 中文说明

    run_migrations()  # 确保调度数据库存在
    with sched_session_scope() as session:  # 打开 Session
        user = session.query(User).filter(User.username == username).one_or_none()  # 查询用户
        if user is None:  # 新用户
            user = User(username=username, role=role, password_hash=password_hash)  # 创建对象
            session.add(user)  # 添加记录
        else:  # 已存在
            user.role = role  # 更新角色
            user.password_hash = password_hash  # 更新密码
            user.is_active = True  # 确保激活


def main() -> None:  # 主函数
    """入口函数：解析参数、校验并创建用户。"""  # 中文说明

    args = parse_args()  # 解析参数
    ensure_admin_token(args.role, args.init_token)  # 校验初始化令牌
    password_hash = prompt_password()  # 读取密码
    create_user(args.username, args.role, password_hash)  # 写入数据库
    print(f"已创建/更新用户 {args.username}，角色 {args.role}")  # 输出结果


if __name__ == "__main__":  # 判断脚本执行
    main()  # 调用主函数
