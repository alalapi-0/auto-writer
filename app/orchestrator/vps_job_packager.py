"""VPS 作业打包模块，负责安全产出 job.json 与临时凭据文件。"""

from __future__ import annotations  # 启用未来注解以兼容类型前向引用

import json  # TODO: 序列化 job payload
import os  # TODO: 设置 .env.runtime 权限，避免泄露
import tempfile  # TODO: 创建隔离的临时目录
from pathlib import Path  # TODO: 使用 Path 处理路径
from typing import Any, Dict, List, Tuple  # TODO: 返回类型涵盖临时目录

from config.settings import BASE_DIR, Settings  # TODO: 引入全局路径与设置类型

SCHEMA_PATH = BASE_DIR / "jobs" / "job.schema.json"  # TODO: JSON Schema 路径
DEFAULT_OUTPUT_DIR = BASE_DIR / "jobs"  # TODO: 默认 job.json 输出目录


def _load_schema() -> Dict[str, Any]:
    """读取 job.schema.json 以便后续校验。"""

    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))  # TODO: 直接解析 JSON 文本


def _validate_topics(topics: List[Dict[str, Any]]) -> None:
    """校验 topics 列表结构，确保符合 schema 要求。"""

    if not isinstance(topics, list):  # TODO: topics 必须是列表
        raise ValueError("topics must be a list")  # TODO: 抛出结构异常
    for topic in topics:  # TODO: 遍历每个主题条目
        if not isinstance(topic, dict):  # TODO: 每个元素必须是字典
            raise ValueError("each topic must be a dict")  # TODO: 抛出异常
        for field in ("character_name", "work", "keyword"):  # TODO: 必填字段集合
            value = topic.get(field)  # TODO: 读取字段值
            if not isinstance(value, str) or not value.strip():  # TODO: 必须是非空字符串
                raise ValueError(f"topic field {field} must be non-empty string")  # TODO: 抛出异常


def _validate_payload(payload: Dict[str, Any]) -> None:
    """根据 schema 对整体 payload 做轻量校验。"""

    schema = _load_schema()  # TODO: 读取 schema
    required_fields = schema.get("required", [])  # TODO: 获取必填字段
    for field in required_fields:  # TODO: 遍历必填项
        if field not in payload:  # TODO: 若缺失
            raise ValueError(f"missing required field: {field}")  # TODO: 抛出异常
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"].strip():
        raise ValueError("run_id must be non-empty string")  # TODO: run_id 必须是非空字符串
    if not isinstance(payload.get("run_date"), str) or not payload["run_date"].strip():
        raise ValueError("run_date must be non-empty string")  # TODO: run_date 必须是非空字符串
    if not isinstance(payload.get("planned_articles"), int) or payload["planned_articles"] <= 0:
        raise ValueError("planned_articles must be positive integer")  # TODO: planned_articles 必须为正整数
    _validate_topics(payload.get("topics", []))  # TODO: 校验 topics 列表
    if not isinstance(payload.get("template_options"), dict):
        raise ValueError("template_options must be a dict")  # TODO: template_options 必须是字典
    if not isinstance(payload.get("delivery_targets"), dict):
        raise ValueError("delivery_targets must be a dict")  # TODO: delivery_targets 必须是字典


def pack_job_and_env(
    settings_obj: Settings,
    run_id: str,
    run_date: str,
    planned_articles: int,
    topics: List[Dict[str, Any]],
    template_options: Dict[str, Any],
    delivery_targets: Dict[str, Any],
    output_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    """生成 job.json 并安全地准备 .env.runtime。"""

    payload = {
        "run_id": run_id,  # TODO: 写入运行 ID
        "run_date": run_date,  # TODO: 写入运行日期
        "planned_articles": planned_articles,  # TODO: 写入计划篇数
        "topics": topics,  # TODO: 写入主题列表
        "template_options": template_options,  # TODO: 写入模板配置
        "delivery_targets": delivery_targets,  # TODO: 写入交付开关
    }
    _validate_payload(payload)  # TODO: 校验 payload 合规性

    target_dir = output_dir or DEFAULT_OUTPUT_DIR  # TODO: 确定输出目录
    target_dir.mkdir(parents=True, exist_ok=True)  # TODO: 确保目录存在

    job_path = target_dir / f"job_{run_id}.json"  # TODO: 生成 job.json 路径
    job_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )  # TODO: 写入 JSON 文件

    temp_dir, env_runtime_path = build_remote_job_env(settings_obj)  # TODO: 生成安全凭据文件

    return job_path, temp_dir, env_runtime_path  # TODO: 返回临时目录供调用方清理


def build_remote_job_env(settings: Settings) -> Tuple[Path, Path]:
    """构建远程作业运行所需的临时目录与 .env.runtime 文件。"""

    temp_dir = Path(tempfile.mkdtemp(prefix="autowriter_"))  # TODO: 创建隔离的临时目录
    env_file = temp_dir / ".env.runtime"  # TODO: 规范临时凭据文件名

    lines: List[str] = []  # TODO: 聚合实际需要的凭据键值
    if settings.enable_wechat_mp and settings.wechat_mp_cookie:
        lines.append(f"WECHAT_MP_COOKIE={settings.wechat_mp_cookie}")
    if settings.enable_zhihu and settings.zhihu_cookie:
        lines.append(f"ZHIHU_COOKIE={settings.zhihu_cookie}")
    if settings.enable_medium and settings.medium_token:
        lines.append(f"MEDIUM_TOKEN={settings.medium_token}")
    if settings.enable_wordpress:
        if settings.wp_url:
            lines.append(f"WP_URL={settings.wp_url}")
        if settings.wp_user:
            lines.append(f"WP_USER={settings.wp_user}")
        if settings.wp_app_pass:
            lines.append(f"WP_APP_PASS={settings.wp_app_pass}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")  # TODO: 写入凭据内容
    os.chmod(env_file, 0o600)  # TODO: 强制权限为 600，避免被其他用户读取

    return temp_dir, env_file  # TODO: 返回供 orchestrator 调用并在 finally 中清理
