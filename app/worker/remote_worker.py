"""VPS 端 worker：加载 job.json，生成草稿并产出 result.json。"""

from __future__ import annotations  # 启用未来注解

import argparse  # 解析命令行参数
import json  # 读写 JSON 文件
from pathlib import Path  # 处理文件路径
from typing import Dict, List  # 类型标注

from app.utils.logger import get_logger  # 引入统一日志模块

LOGGER = get_logger(__name__)  # 初始化模块日志记录器


def _load_job(path: Path) -> dict:
    """读取 job.json 文件。"""

    return json.loads(path.read_text(encoding="utf-8"))  # 解析 JSON


def _load_env(path: Path) -> Dict[str, str]:
    """解析 .env.runtime 文件为字典。"""

    env_data: Dict[str, str] = {}  # 初始化结果
    if not path.exists():  # 若文件不存在
        return env_data  # 返回空字典
    for line in path.read_text(encoding="utf-8").splitlines():  # 遍历每一行
        if not line.strip() or line.strip().startswith("#"):  # 跳过空行与注释
            continue  # 继续下一行
        key, _, value = line.partition("=")  # 拆分键值
        env_data[key.strip()] = value.strip()  # 写入字典
    return env_data  # 返回解析结果


def _render_article(topic: dict, template_options: dict) -> str:
    """根据模板选项渲染示例文章。"""

    return (
        f"【{template_options.get('style', 'analysis')}】"
        f"{topic['character_name']} × {topic['work']} —— 结合关键词 {topic['keyword']} 的心理剖析"
    )  # 简单拼接示例正文


def _deliver(platform: str, credentials: Dict[str, str]) -> dict:
    """模拟投递行为，凭据存在则视为成功。"""

    prefix = platform.upper()  # 规范化平台名称
    ok = any(key.startswith(prefix) and value for key, value in credentials.items())  # 至少存在一个相关凭据即视为成功
    if ok:
        return {"platform": platform, "ok": True, "id_or_url": f"{platform}-draft-id"}  # 返回成功结果
    return {"platform": platform, "ok": False, "error": "credential_missing"}  # 返回失败信息


def main() -> None:
    """命令行入口，执行本地渲染与结果回传。"""

    parser = argparse.ArgumentParser(description="AutoWriter Remote Worker")  # 构建参数解析器
    parser.add_argument("--job", required=True, help="job.json 路径")  # job.json 路径
    parser.add_argument("--env", required=True, help=".env.runtime 路径")  # 环境变量文件
    parser.add_argument("--output", required=True, help="result.json 输出路径")  # result.json 路径
    parser.add_argument("--log", required=True, help="日志文件路径")  # worker 日志路径
    args = parser.parse_args()  # 解析参数

    job_path = Path(args.job)  # 转换为 Path
    env_path = Path(args.env)  # 转换为 Path
    output_path = Path(args.output)  # 输出路径
    log_path = Path(args.log)  # 日志路径

    LOGGER.info("远程 worker 启动 job=%s env=%s", str(job_path), str(env_path))  # 记录启动信息
    job_data = _load_job(job_path)  # 读取 job.json
    runtime_env = _load_env(env_path)  # 读取 .env.runtime

    articles_result: List[dict] = []  # 准备结果列表
    overall_success = True  # 新增: 聚合成功标记
    error_messages: List[str] = []  # 新增: 收集错误信息
    for topic in job_data.get("topics", []):  # 遍历任务
        LOGGER.info(  # 记录主题处理开始
            "处理主题 character=%s work=%s keyword=%s",
            topic.get("character_name"),
            topic.get("work"),
            topic.get("keyword"),
        )
        content = _render_article(topic, job_data.get("template_options", {}))  # 渲染正文
        platform_results = []  # 平台结果列表
        for platform, enabled in job_data.get("delivery_targets", {}).items():  # 遍历交付目标
            if not enabled:  # 若未开启
                continue  # 跳过
            result = _deliver(platform, runtime_env)  # 新增: 调用投递模拟
            LOGGER.info(  # 记录平台投递结果
                "平台处理结果 platform=%s ok=%s error=%s",
                platform,
                result.get("ok"),
                result.get("error"),
            )
            if not result.get("ok"):  # 新增: 检测失败
                overall_success = False  # 新增: 标记整体失败
                error_messages.append(f"{platform}:{result.get('error')}")  # 新增: 记录错误
            platform_results.append(result)  # 新增: 收录结果
        articles_result.append(
            {
                "character_name": topic["character_name"],
                "work": topic["work"],
                "keyword": topic["keyword"],
                "status": "draft_pushed" if platform_results else "generated",
                "content": content,
                "platform_results": platform_results,
            }
        )  # 收录结果

    result_payload = {
        "run_id": job_data.get("run_id", ""),
        "success": overall_success,  # 新增: 根据聚合结果返回
        "articles": articles_result,
        "errors": error_messages,  # 新增: 返回错误列表
    }  # 构造 result.json
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 确保结果目录存在
    output_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 写入 result.json
    log_path.parent.mkdir(parents=True, exist_ok=True)  # 确保日志目录存在
    log_lines = [
        "[remote_worker] start",
        f"topics={len(job_data.get('topics', []))}",
        f"success={overall_success}",
        "[remote_worker] finish",
    ]  # 构造日志内容
    log_path.write_text("\n".join(log_lines), encoding="utf-8")  # 写入日志
    LOGGER.info("远程 worker 完成 output=%s success=%s", str(output_path), overall_success)  # 记录完成信息

    if env_path.exists():  # 任务完成后删除 .env.runtime
        env_path.unlink()  # 删除文件
        LOGGER.info("清理 runtime 环境文件 path=%s", str(env_path))  # 记录清理动作


if __name__ == "__main__":  # 脚本入口
    main()  # 执行主函数
