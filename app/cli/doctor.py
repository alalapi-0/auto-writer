# -*- coding: utf-8 -*-  # 指定 UTF-8 编码，确保中文注释兼容
"""应用自检命令，实现配置、数据库、目录与平台状态巡检。"""  # 模块文档说明

from __future__ import annotations  # 启用未来注解语法提高兼容性

import importlib  # 动态导入平台适配器验证可用性
import sys  # 访问退出码控制流程
from dataclasses import dataclass  # 使用数据类描述检查结果
from datetime import datetime, timedelta  # 处理时间窗口
from pathlib import Path  # 统一处理路径对象
from typing import List  # 类型提示

from sqlalchemy import inspect, text  # 数据库元信息查询与执行原生 SQL
from sqlalchemy.exc import SQLAlchemyError  # 捕获 SQLAlchemy 异常

from config.settings import (  # 导入配置及目录常量
    ENV_PATH,  # .env 文件路径
    EXPORT_DIR,  # 导出目录配置
    LOG_DIR,  # 日志目录配置
    OUTBOX_DIR,  # 草稿目录配置
    settings,  # 全局配置实例
    print_config,  # 配置打印函数
)
from app.db.migrate import get_engine, SessionLocal  # 数据库引擎与 Session 工厂
from app.utils.logger import get_logger  # 统一日志模块

STATUS_OK = "✅"  # 成功状态图标
STATUS_WARN = "⚠️"  # 警告状态图标
STATUS_FAIL = "❌"  # 失败状态图标


@dataclass
class CheckResult:  # 定义检查结果数据结构
    name: str  # 检查项名称
    status: str  # 状态图标
    message: str  # 详细说明


LOGGER = get_logger(__name__)  # 初始化自检日志记录器


def _make_result(name: str, status: str, message: str) -> CheckResult:
    """构造带日志的检查结果。"""  # 函数中文说明

    LOGGER.info("doctor_check item=%s status=%s message=%s", name, status, message)  # 记录检查日志
    return CheckResult(name=name, status=status, message=message)  # 返回数据结构


def _check_env_file() -> CheckResult:
    """检查 .env 文件是否存在。"""

    if ENV_PATH.exists():  # 判断 .env 是否存在
        return _make_result("环境文件", STATUS_OK, f"存在 {ENV_PATH}")  # 返回成功结果
    return _make_result("环境文件", STATUS_WARN, f"未找到 {ENV_PATH}，请确认部署流程")  # 返回警告


def _check_directories() -> List[CheckResult]:
    """检查关键目录的可写性并进行 .probe 测试。"""

    results: List[CheckResult] = []  # 初始化结果列表
    for label, raw_path in (
        ("OUTBOX 目录", OUTBOX_DIR),  # 草稿输出目录
        ("LOG 目录", LOG_DIR),  # 日志目录
        ("EXPORT 目录", EXPORT_DIR),  # 导出目录
    ):  # 遍历目录配置
        path = Path(raw_path).expanduser()  # 解析路径
        try:  # 捕获文件系统异常
            path.mkdir(parents=True, exist_ok=True)  # 确保目录存在
            probe = path / ".probe"  # 定义探针文件
            probe.write_text("doctor", encoding="utf-8")  # 写入测试内容
            probe.unlink(missing_ok=True)  # 删除测试文件
            results.append(_make_result(label, STATUS_OK, f"{path} 可写"))  # 记录成功
        except Exception as exc:  # noqa: BLE001  # 捕获所有异常
            results.append(_make_result(label, STATUS_FAIL, f"{path} 不可写: {exc}"))  # 记录失败
    return results  # 返回目录检查结果


def _check_config_values() -> List[CheckResult]:
    """校验配置值合法性并输出关键配置。"""

    results: List[CheckResult] = []  # 初始化结果列表
    print_config(mask_secrets=True)  # 打印配置概览
    if settings.database.url:  # 检查数据库 URL
        results.append(_make_result("数据库配置", STATUS_OK, settings.database.url))  # 记录成功
    else:
        results.append(_make_result("数据库配置", STATUS_FAIL, "未配置数据库 URL"))  # 记录失败
    if settings.delivery_enabled_platforms:  # 判断是否配置平台列表
        allowed = {"wechat_mp", "zhihu"}  # 允许的平台集合
        invalid = [p for p in settings.delivery_enabled_platforms if p not in allowed]  # 收集非法平台
        if invalid:  # 存在非法值
            results.append(_make_result("启用平台", STATUS_FAIL, f"非法平台: {','.join(invalid)}"))  # 记录失败
        else:
            results.append(_make_result("启用平台", STATUS_OK, ",".join(settings.delivery_enabled_platforms)))  # 记录成功
    else:
        results.append(_make_result("启用平台", STATUS_WARN, "当前未启用任何平台"))  # 提示可选
    if settings.database.url.startswith("sqlite:///"):  # 若使用 SQLite
        db_path = Path(settings.database.url.replace("sqlite:///", "")).expanduser()  # 解析路径
        try:  # 捕获 IO 异常
            db_path.parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在
            probe = db_path.parent / ".db.probe"  # 探针文件
            probe.write_text("ok", encoding="utf-8")  # 写入测试
            probe.unlink(missing_ok=True)  # 删除探针
            results.append(_make_result("SQLite 写权限", STATUS_OK, f"目录 {db_path.parent} 可写"))  # 成功
        except Exception as exc:  # noqa: BLE001  # 捕获异常
            results.append(_make_result("SQLite 写权限", STATUS_FAIL, f"目录不可写: {exc}"))  # 失败
    return results  # 返回配置检查结果


def _check_db_schema(session) -> List[CheckResult]:
    """验证数据库连接与必须表是否存在。"""

    results: List[CheckResult] = []  # 初始化结果列表
    try:  # 捕获数据库异常
        with session.begin():  # 开启事务
            session.execute(text("SELECT 1"))  # 执行探活查询
        results.append(_make_result("数据库连接", STATUS_OK, "连接成功"))  # 记录成功
    except SQLAlchemyError as exc:  # 捕获数据库异常
        results.append(_make_result("数据库连接", STATUS_FAIL, f"连接失败: {exc}"))  # 记录失败
        return results  # 无需继续检查
    engine = session.get_bind()  # 获取底层引擎
    inspector = inspect(engine)  # 创建元信息检查器
    required_tables = [  # 定义必须存在的表集合
        "articles",
        "platform_logs",
        "runs",
        "keywords",
        "used_pairs",
        "psychology_themes",
    ]
    missing = [table for table in required_tables if not inspector.has_table(table)]  # 计算缺失表
    if missing:  # 若存在缺失
        results.append(
            _make_result(
                "数据库表结构",
                STATUS_FAIL,
                f"缺失数据表: {', '.join(missing)}，请执行迁移",
            )
        )
    else:
        results.append(_make_result("数据库表结构", STATUS_OK, "核心数据表齐全"))  # 所有表存在
    return results  # 返回检查结果


def _check_theme_inventory(session) -> List[CheckResult]:
    """统计主题库存并输出近 7 天消耗情况。"""

    results: List[CheckResult] = []  # 初始化结果列表
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()  # 计算 7 天窗口
    try:  # 捕获数据库异常
        with session.begin():  # 开启事务
            count_stmt = text(
                "SELECT COUNT(*) FROM psychology_themes WHERE (used IS NULL OR used = 0)"
            )  # 未使用主题统计
            remaining = session.execute(count_stmt).scalar() or 0  # 获取剩余数量
            history_stmt = text(
                """
                SELECT substr(used_at, 1, 10) AS day, COUNT(*) AS cnt
                FROM psychology_themes
                WHERE used_at IS NOT NULL AND used_at >= :cutoff
                GROUP BY day
                ORDER BY day DESC
                """
            )  # 构造近 7 天消耗统计 SQL
            history = session.execute(history_stmt, {"cutoff": cutoff}).mappings().all()  # 执行查询
        status = STATUS_OK if remaining >= settings.theme_low_watermark else STATUS_WARN  # 根据阈值决定状态
        message = (
            f"剩余 {remaining} 条，阈值 {settings.theme_low_watermark}"
            if history
            else f"剩余 {remaining} 条，近 7 天无消耗记录"
        )  # 组合提示文案
        results.append(_make_result("主题库存", status, message))  # 添加库存结果
        if history:  # 若存在历史记录
            breakdown = ", ".join(f"{row['day']}: {row['cnt']}" for row in history)  # 构造详情
            results.append(_make_result("近 7 天消耗", STATUS_OK, breakdown))  # 添加消耗明细
        else:
            results.append(_make_result("近 7 天消耗", STATUS_WARN, "暂无使用记录"))  # 添加提示
    except SQLAlchemyError as exc:  # 捕获异常
        results.append(_make_result("主题库存", STATUS_FAIL, f"统计失败: {exc}"))  # 记录失败
    return results  # 返回统计结果


def _check_dirty_locks(session) -> List[CheckResult]:
    """检测残留的主题软锁并提供解锁建议。"""

    results: List[CheckResult] = []  # 初始化结果列表
    try:  # 捕获数据库异常
        with session.begin():  # 开启事务
            lock_stmt = text(
                "SELECT id, locked_by_run_id FROM psychology_themes WHERE locked_by_run_id IS NOT NULL"
            )  # 查询残留软锁
            locked_rows = session.execute(lock_stmt).mappings().all()  # 执行查询
        if locked_rows:  # 存在残留
            run_ids = {row["locked_by_run_id"] for row in locked_rows if row["locked_by_run_id"]}  # 收集运行 ID
            suggestion = (
                "UPDATE psychology_themes SET locked_by_run_id=NULL, locked_at=NULL "
                "WHERE locked_by_run_id IS NOT NULL;"
            )  # 解锁 SQL 提示
            message = f"残留 {len(locked_rows)} 条锁，涉及运行 {', '.join(sorted(run_ids))}; 建议执行: {suggestion}"  # 提示信息
            results.append(_make_result("主题软锁", STATUS_WARN, message))  # 添加警告
        else:
            results.append(_make_result("主题软锁", STATUS_OK, "无残留软锁"))  # 添加成功
    except SQLAlchemyError as exc:  # 捕获异常
        results.append(_make_result("主题软锁", STATUS_FAIL, f"检查失败: {exc}"))  # 记录失败
    return results  # 返回检查结果


def _check_platform_modules() -> List[CheckResult]:
    """检查启用平台的适配器模块是否可导入。"""

    results: List[CheckResult] = []  # 初始化结果列表
    if not settings.delivery_enabled_platforms:  # 若未启用平台
        results.append(_make_result("平台适配器", STATUS_WARN, "未启用任何平台，后续请根据需求开启"))  # 添加提示
        return results  # 直接返回
    for platform in settings.delivery_enabled_platforms:  # 遍历平台
        module_name = f"app.delivery.{platform}_adapter"  # 构造模块名
        try:  # 捕获导入异常
            importlib.import_module(module_name)  # 动态导入模块
            results.append(_make_result("平台模块", STATUS_OK, f"{module_name} 可导入"))  # 添加成功
        except Exception as exc:  # noqa: BLE001  # 捕获所有异常
            results.append(_make_result("平台模块", STATUS_FAIL, f"{module_name} 导入失败: {exc}"))  # 添加失败
    results.append(_make_result("Playwright 准备", STATUS_WARN, "Round5 将引入 Playwright，请预留依赖环境"))  # 提示未来计划
    return results  # 返回结果


def run_doctor() -> int:
    """执行全部检查并返回退出码。"""

    LOGGER.info("doctor_start")  # 记录自检开始
    results: List[CheckResult] = []  # 初始化结果列表
    results.append(_check_env_file())  # 检查 .env
    results.extend(_check_directories())  # 检查目录权限
    results.extend(_check_config_values())  # 检查配置
    session = None  # 初始化会话引用
    try:  # 捕获数据库初始化异常
        engine = get_engine()  # 创建数据库引擎
        session = SessionLocal(bind=engine)  # 基于引擎创建 Session
        results.extend(_check_db_schema(session))  # 检查数据库结构
        results.extend(_check_theme_inventory(session))  # 检查主题库存
        results.extend(_check_dirty_locks(session))  # 检查软锁
    except SQLAlchemyError as exc:  # 捕获数据库异常
        results.append(_make_result("数据库检查", STATUS_FAIL, f"数据库异常: {exc}"))  # 记录失败
    finally:  # 无论成功失败均执行
        if session is not None:  # 会话存在时
            session.close()  # 关闭会话
    results.extend(_check_platform_modules())  # 检查平台模块
    has_fail = any(item.status == STATUS_FAIL for item in results)  # 判断是否存在失败
    for item in results:  # 逐条输出
        print(f"{item.status} {item.name}: {item.message}")  # 打印检查结果
    LOGGER.info("doctor_finish failed=%s", has_fail)  # 记录结束状态
    return 1 if has_fail else 0  # 返回退出码


def main() -> None:
    """命令行入口，包装 run_doctor 并处理退出码。"""

    exit_code = run_doctor()  # 执行自检
    if exit_code != 0:  # 若检测失败
        sys.exit(exit_code)  # 返回非零退出码


if __name__ == "__main__":  # 判断脚本直接执行
    main()  # 调用入口
