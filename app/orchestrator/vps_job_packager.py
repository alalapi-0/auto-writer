"""VPS 作业打包模块。"""

from __future__ import annotations  # 启用未来注解以兼容类型前向引用

import json  # 处理 JSON 序列化
from dataclasses import asdict  # 将数据类转换为字典
from pathlib import Path  # 处理文件路径
from typing import Any, Dict, List  # 类型标注别名

from config.settings import BASE_DIR  # 导入仓库根路径
from config.settings import Settings  # 引入配置类型以便类型提示

SCHEMA_PATH = BASE_DIR / "jobs" / "job.schema.json"  # Schema 文件路径
DEFAULT_OUTPUT_DIR = BASE_DIR / "jobs"  # 默认输出目录


def _load_schema() -> Dict[str, Any]:
    """读取 job.schema.json 以便后续校验。"""

    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))  # 直接解析 JSON 文本


def _validate_topics(topics: List[Dict[str, Any]]) -> None:
    """校验 topics 列表结构，确保符合 schema 要求。"""

    if not isinstance(topics, list):  # topics 必须是列表
        raise ValueError("topics must be a list")  # 抛出结构异常
    for topic in topics:  # 遍历每个主题条目
        if not isinstance(topic, dict):  # 每个元素必须是字典
            raise ValueError("each topic must be a dict")  # 抛出异常
        for field in ("character_name", "work", "keyword"):  # 必填字段集合
            value = topic.get(field)  # 读取字段值
            if not isinstance(value, str) or not value.strip():  # 必须是非空字符串
                raise ValueError(f"topic field {field} must be non-empty string")  # 抛出异常


def _validate_payload(payload: Dict[str, Any]) -> None:
    """根据 schema 对整体 payload 做轻量校验。"""

    schema = _load_schema()  # 读取 schema
    required_fields = schema.get("required", [])  # 获取必填字段
    for field in required_fields:  # 遍历必填项
        if field not in payload:  # 若缺失
            raise ValueError(f"missing required field: {field}")  # 抛出异常
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"].strip():  # run_id 必须是非空字符串
        raise ValueError("run_id must be non-empty string")  # 抛出异常
    if not isinstance(payload.get("run_date"), str) or not payload["run_date"].strip():  # run_date 必须是字符串
        raise ValueError("run_date must be non-empty string")  # 抛出异常
    if not isinstance(payload.get("planned_articles"), int) or payload["planned_articles"] <= 0:  # planned_articles 必须为正整数
        raise ValueError("planned_articles must be positive integer")  # 抛出异常
    _validate_topics(payload.get("topics", []))  # 校验 topics 列表
    if not isinstance(payload.get("template_options"), dict):  # template_options 必须是字典
        raise ValueError("template_options must be a dict")  # 抛出异常
    if not isinstance(payload.get("delivery_targets"), dict):  # delivery_targets 必须是字典
        raise ValueError("delivery_targets must be a dict")  # 抛出异常


def pack_job_and_env(
    settings_obj: Settings,
    run_id: str,
    run_date: str,
    planned_articles: int,
    topics: List[Dict[str, Any]],
    template_options: Dict[str, Any],
    delivery_targets: Dict[str, Any],
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """生成 job.json 与 .env.runtime 文件。"""

    payload = {
        "run_id": run_id,  # 写入运行 ID
        "run_date": run_date,  # 写入运行日期
        "planned_articles": planned_articles,  # 写入计划篇数
        "topics": topics,  # 写入主题列表
        "template_options": template_options,  # 写入模板配置
        "delivery_targets": delivery_targets,  # 写入交付开关
    }
    _validate_payload(payload)  # 校验 payload 合规性

    target_dir = output_dir or DEFAULT_OUTPUT_DIR  # 确定输出目录
    target_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在

    job_path = target_dir / f"job_{run_id}.json"  # 生成 job.json 路径
    job_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 写入 JSON 文件

    credentials_dict = asdict(settings_obj.platform_credentials)  # 转换平台凭据
    env_lines = [f"{key.upper()}={value}" for key, value in credentials_dict.items() if value]  # 仅输出非空凭据
    env_runtime_path = target_dir / ".env.runtime"  # 生成 .env.runtime 路径
    env_runtime_path.write_text("\n".join(env_lines), encoding="utf-8")  # 写入环境变量文本

    return job_path, env_runtime_path  # 返回路径元组
