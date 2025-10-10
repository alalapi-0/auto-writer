"""Profile 档案加载与校验模块。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

from pathlib import Path  # 处理文件路径
from typing import Dict, List  # 类型提示

import yaml  # 解析 YAML

from config.settings import settings  # 导入全局配置
from app.db.migrate_sched import sched_session_scope  # 调度库 Session 上下文
from app.db.models_sched import Profile  # Profile ORM 模型
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志记录器

REQUIRED_ROOT_KEYS = {"name", "generation", "delivery"}  # 定义必填顶层字段
ALLOWED_DISPATCH_MODES = {"queue", "local"}  # 允许的调度模式集合


def _load_yaml(path: Path) -> Dict:  # 定义内部工具函数
    """读取并解析单个 YAML 文件。"""  # 中文说明

    LOGGER.info("加载 profile 文件 path=%s", path)  # 记录日志
    data = yaml.safe_load(path.read_text(encoding="utf-8"))  # 读取并解析 YAML
    if not isinstance(data, dict):  # 校验解析结果
        raise ValueError(f"Profile 文件格式错误: {path}")  # 抛出异常
    return data  # 返回字典


def validate_profile(data: Dict) -> None:  # 校验函数
    """验证 Profile 数据结构合法性，不返回值，失败抛异常。"""  # 中文说明

    missing = REQUIRED_ROOT_KEYS - data.keys()  # 计算缺失字段
    if missing:  # 若存在缺失
        raise ValueError(f"Profile 缺少字段: {','.join(sorted(missing))}")  # 抛出异常
    if "name" in data and not data["name"]:  # 校验名称
        raise ValueError("Profile 名称不能为空")  # 抛出异常
    generation = data.get("generation", {})  # 获取生成配置
    if not isinstance(generation, dict):  # 校验类型
        raise ValueError("generation 字段必须是对象")  # 抛出异常
    if generation.get("articles_per_day", 0) <= 0:  # 校验篇数
        raise ValueError("articles_per_day 必须大于 0")  # 抛出异常
    delivery = data.get("delivery", {})  # 获取投递配置
    if not isinstance(delivery, dict):  # 校验类型
        raise ValueError("delivery 字段必须是对象")  # 抛出异常
    platforms = delivery.get("platforms", [])  # 读取平台列表
    if not isinstance(platforms, list) or not platforms:  # 校验平台列表
        raise ValueError("platforms 必须为非空数组")  # 抛出异常
    window = delivery.get("window", {})  # 获取窗口设置
    if not isinstance(window, dict) or "start" not in window or "end" not in window:  # 校验窗口
        raise ValueError("delivery.window 必须包含 start/end")  # 抛出异常
    dispatch_mode = data.get("dispatch_mode", "queue")  # 读取调度模式
    if dispatch_mode not in ALLOWED_DISPATCH_MODES:  # 校验模式合法性
        raise ValueError("dispatch_mode 必须是 queue 或 local")  # 抛出异常


def _ensure_directory() -> Path:  # 确保目录存在
    """确保 profiles 目录存在并返回 Path 对象。"""  # 中文说明

    path = Path(settings.profiles_dir).expanduser()  # 解析目录
    path.mkdir(parents=True, exist_ok=True)  # 创建目录
    return path  # 返回 Path


def sync_profiles() -> List[Profile]:  # 同步函数
    """读取目录内所有 YAML 并同步到数据库。"""  # 中文说明

    directory = _ensure_directory()  # 获取目录
    profiles: List[Profile] = []  # 准备返回列表
    yaml_files = sorted(directory.glob("*.yml"))  # 查找 YAML 文件
    with sched_session_scope() as session:  # 打开 Session
        for yaml_path in yaml_files:  # 遍历文件
            data = _load_yaml(yaml_path)  # 解析 YAML
            validate_profile(data)  # 校验数据
            name = data["name"]  # 获取名称
            enabled = bool(data.get("enabled", True))  # 获取启用状态
            dispatch_mode = data.get("dispatch_mode", "queue")  # 获取调度模式
            record = session.query(Profile).filter(Profile.name == name).one_or_none()  # 查询现有记录
            if record is None:  # 若不存在
                record = Profile(  # 创建对象
                    name=name,  # 设置名称
                    yaml_path=str(yaml_path),  # 设置 YAML 路径
                    is_enabled=enabled,  # 设置启用状态
                    dispatch_mode=dispatch_mode,  # 设置调度模式
                )
                session.add(record)  # 添加到 Session
                LOGGER.info("新增 profile name=%s", name)  # 记录日志
            else:  # 已存在
                record.yaml_path = str(yaml_path)  # 更新路径
                record.is_enabled = enabled  # 更新启用状态
                record.dispatch_mode = dispatch_mode  # 更新调度模式
                LOGGER.info("更新 profile name=%s", name)  # 记录日志
            profiles.append(record)  # 加入返回列表
    return profiles  # 返回同步结果


def list_profiles() -> List[Dict]:  # 列表函数
    """列出数据库中的 Profile 信息。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        rows = session.query(Profile).order_by(Profile.name.asc()).all()  # 查询全部
        return [  # 构造字典列表
            {
                "id": row.id,
                "name": row.name,
                "yaml_path": row.yaml_path,
                "enabled": row.is_enabled,
                "dispatch_mode": row.dispatch_mode,
            }
            for row in rows
        ]


def get_profile(name: str) -> Dict | None:  # 获取单个 Profile
    """根据名称返回 Profile 字典，未找到返回 None。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        row = session.query(Profile).filter(Profile.name == name).one_or_none()  # 查询
        if row is None:  # 未找到
            return None  # 返回 None
        return {  # 返回字段字典
            "id": row.id,
            "name": row.name,
            "yaml_path": row.yaml_path,
            "enabled": row.is_enabled,
        }


if __name__ == "__main__":  # 允许独立运行
    sync_profiles()  # 执行同步
