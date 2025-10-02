"""本机 orchestrator 入口：规划→打包→传输→回收→补全。"""

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
from datetime import date, datetime, timedelta  # 处理日期与时间
from typing import List  # 类型别名

from sqlalchemy import or_, select  # 构造查询条件
from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from config.settings import settings  # 导入全局配置
from app.db import models  # 导入 ORM 模型
from app.db.migrate import SessionLocal  # 获取 Session 工厂
from app.orchestrator import parsers, ssh_runner, vps_job_packager  # 引入 orchestrator 子模块


def _split_traits(traits: str) -> List[str]:
    """将逗号或中文顿号分隔的特质拆分成列表。"""

    separators = [",", "，", "、"]  # 定义常见分隔符
    normalized = traits  # 复制原始字符串
    for sep in separators:  # 遍历分隔符
        normalized = normalized.replace(sep, "|")  # 统一替换为竖线
    return [item.strip() for item in normalized.split("|") if item.strip()]  # 去除空白并过滤空项


def _find_character_for_keyword(session: Session, keyword: str) -> dict:
    """根据关键词在角色库中寻找最匹配的角色。"""

    keyword_lower = keyword.lower()  # 小写化关键词
    characters = session.execute(select(models.Character)).scalars().all()  # 查询主角色库
    for character in characters:  # 优先从主库匹配
        traits = _split_traits(character.traits)  # 拆分特质
        if any(keyword_lower in trait.lower() for trait in traits):  # 若命中特质
            return {"character_name": character.name, "work": character.work}  # 返回匹配角色
    extended_characters = session.execute(select(models.ExtendedCharacter)).scalars().all()  # 查询扩展角色库
    for character in extended_characters:  # 再尝试扩展库
        traits = _split_traits(character.traits)  # 拆分特质
        if any(keyword_lower in trait.lower() for trait in traits):  # 若命中
            return {"character_name": character.name, "work": character.work}  # 返回匹配
    if characters:  # 若未匹配则兜底使用主库第一条
        fallback = characters[0]  # 取第一条记录
        return {"character_name": fallback.name, "work": fallback.work}  # 返回兜底角色
    raise ValueError("角色库为空，无法匹配关键词")  # 若完全无角色则报错


def plan_topics(session: Session, target_count: int, cooldown_days: int) -> List[dict]:
    """规划当日主题，优先选择未使用或冷却期外的关键词。"""

    now = datetime.utcnow()  # 获取当前时间
    cutoff = now - timedelta(days=cooldown_days)  # 计算冷却时间
    keyword_stmt = (
        select(models.Keyword)
        .where(models.Keyword.is_active.is_(True))
        .where(
            or_(
                models.Keyword.last_used_at.is_(None),
                models.Keyword.last_used_at <= cutoff,
            )
        )
        .order_by(models.Keyword.last_used_at.isnot(None), models.Keyword.last_used_at.asc(), models.Keyword.created_at.asc())
    )  # 构造查询语句
    keywords = session.execute(keyword_stmt).scalars().all()  # 执行查询
    plan: List[dict] = []  # 准备选题列表
    for keyword_record in keywords:  # 遍历候选关键词
        character_info = _find_character_for_keyword(session, keyword_record.keyword)  # 匹配角色
        topic = {
            "character_name": character_info["character_name"],
            "work": character_info["work"],
            "keyword": keyword_record.keyword,
        }  # 组装主题结构
        plan.append(topic)  # 收录主题
        if len(plan) >= target_count:  # 达到目标数量
            break  # 结束循环
    return plan  # 返回选题计划


def preflight_scan(session: Session, topics: List[dict], run_date: date) -> List[dict]:
    """执行生成前去重，避免当日重复。"""

    deduped: List[dict] = []  # 存放去重后的主题
    seen = set()  # 记录当日已选组合
    for topic in topics:  # 遍历主题
        key = (topic["character_name"], topic["work"], topic["keyword"])  # 构造组合键
        if key in seen:  # 若在本次计划中重复
            continue  # 跳过
        conflict = (
            session.query(models.UsedPair)
            .filter(
                models.UsedPair.character_name == topic["character_name"],
                models.UsedPair.work == topic["work"],
                models.UsedPair.keyword == topic["keyword"],
                models.UsedPair.used_on == run_date,
            )
            .first()
        )  # 查询当日是否已使用
        if conflict:  # 若当日已使用
            continue  # 跳过
        # TODO: 在此处集成相似度哈希扫描，避免高相似内容
        seen.add(key)  # 记录组合
        deduped.append(topic)  # 收录主题
    return deduped  # 返回去重结果


def build_job_payload(run_id: str, run_date: date, topics: List[dict]) -> dict:
    """组装 job.json 所需的基础数据结构。"""

    return {
        "run_id": run_id,
        "run_date": run_date.isoformat(),
        "planned_articles": len(topics),
        "topics": topics,
        "template_options": {"style": "psychology_analysis"},
        "delivery_targets": {"wordpress": True, "medium": True, "wechat": False},
    }  # 返回字典


def orchestrate(run_date: date, target_articles: int | None = None) -> dict:
    """执行 orchestrator 全流程并返回概要信息。"""

    target = target_articles or settings.orchestrator.daily_article_count  # 确定目标篇数
    run_id = f"{run_date.isoformat()}-{datetime.utcnow().strftime('%H%M%S')}"  # 生成 run_id
    with SessionLocal() as session:  # 创建数据库会话
        run_record = models.Run(  # 初始化 run 记录
            run_id=run_id,
            run_date=run_date,
            planned_articles=target,
            status="planning",
        )
        session.add(run_record)  # 写入 run 表
        session.commit()  # 提交以获得 ID

        topics = plan_topics(
            session,
            target,
            settings.orchestrator.keyword_recent_cooldown_days,
        )  # 调用规划器
        topics = preflight_scan(session, topics, run_date)  # 执行去重
        if not topics:  # 若无可用主题
            run_record.status = "skipped"  # 标记为跳过
            session.commit()  # 持久化状态
            return {"run_id": run_id, "topics": []}  # 直接返回
        payload = build_job_payload(run_id, run_date, topics)  # 组装 payload
        job_path, env_runtime_path = vps_job_packager.pack_job_and_env(
            settings,
            payload["run_id"],
            payload["run_date"],
            payload["planned_articles"],
            payload["topics"],
            payload["template_options"],
            payload["delivery_targets"],
        )  # 打包 job.json 与 .env.runtime

        run_record.planned_articles = len(topics)  # 更新实际计划篇数
        run_record.metadata_path = str(job_path)  # 记录 job.json 路径
        session.commit()  # 提交更新

        runner = ssh_runner.SSHRunner(settings.ssh)  # 初始化 SSH 运行器
        result_summary: dict = {
            "run_id": run_id,
            "topics": topics,
            "job_path": str(job_path),
            "env_runtime_path": str(env_runtime_path),
        }  # 准备返回概要

        if runner.is_configured and topics:  # 若配置完整且存在任务
            runner.stage_files(job_path, env_runtime_path)  # 拷贝文件到 VPS 工作目录
            runner.run_remote_worker()  # 执行远程 worker
            result_path, log_path = runner.collect_results()  # 获取结果路径
            run_record.result_path = str(result_path)  # 记录 result.json 路径
            session.commit()  # 提交更新

            result_data = parsers.load_result_json(result_path)  # 读取 result.json
            consumed = parsers.persist_results(session, run_record, result_data)  # 落表
            if settings.orchestrator.enable_postrun_enrich:  # 若开启补充策略
                parsers.perform_postrun_enrich(
                    session,
                    run_record,
                    consumed,
                    settings.orchestrator.postrun_enrich_group_size,
                )  # 执行补词
            runner.cleanup_remote_env()  # 删除远程环境变量文件
            result_summary["result_path"] = str(result_path)  # 更新概要
            result_summary["log_path"] = str(log_path)  # 更新概要
        else:
            run_record.status = "scheduled"  # 若未执行远程则标记为已规划
            session.commit()  # 提交状态
        return result_summary  # 返回 orchestrator 结果


def main() -> None:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="AutoWriter Orchestrator")  # 构建参数解析器
    parser.add_argument("--date", help="运行日期，格式 YYYY-MM-DD", required=False)  # 可选日期参数
    parser.add_argument("--articles", type=int, help="目标文章数", required=False)  # 可选篇数参数
    args = parser.parse_args()  # 解析参数

    run_date = date.fromisoformat(args.date) if args.date else date.today()  # 解析运行日期
    orchestrate(run_date, args.articles)  # 执行 orchestrator


if __name__ == "__main__":  # 脚本入口
    main()  # 调用主函数
