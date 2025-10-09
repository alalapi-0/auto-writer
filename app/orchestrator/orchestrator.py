"""本机 orchestrator 入口：规划→打包→传输→回收→补全。"""

from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
from datetime import date, datetime, timedelta, timezone  # TODO: 增加 timezone 以便软锁记录
from typing import List  # 类型别名

from sqlalchemy import or_, select, text  # 构造查询条件与手写 SQL
from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from config.settings import settings  # 导入全局配置
from app.db import models  # 导入 ORM 模型
from app.delivery.dispatcher import deliver_article_to_all  # 新增: 引入平台分发器
from app.db.migrate import SessionLocal  # 获取 Session 工厂
from app.orchestrator import parsers, ssh_runner, vps_job_packager  # 引入 orchestrator 子模块
from app.generator.article_generator import lease_theme_for_run, release_theme_lock  # TODO: 导入软锁操作
from app.generator.persistence import insert_article_tx  # 新增导入用于执行去重与事务落库


def _update_run(db: Session, run_id: str, status: str, error: str | None = None) -> None:
    """将运行状态写入 runs 表，若不存在则创建。"""  # 新增: 函数中文文档

    now = datetime.utcnow()  # 新增: 获取当前 UTC 时间
    run_date = now.date()  # 新增: 取当日日期
    trans = db.begin()  # 新增: 开启事务
    try:
        db.execute(  # 新增: 执行 UPSERT 语句
            text(
                """
                INSERT INTO runs (run_id, run_date, planned_articles, status, error, created_at, updated_at)
                VALUES (:run_id, :run_date, 0, :status, :error, :now, :now)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """
            ),
            {"run_id": run_id, "run_date": run_date, "status": status, "error": error, "now": now},
        )
        trans.commit()  # 新增: 提交事务
    except Exception:
        trans.rollback()  # 新增: 出错回滚
        raise  # 新增: 向上抛出异常


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


def finalize_theme_used(db: Session, theme_id: int, run_id: str) -> None:
    """所有投递成功后，最终落地 used 标记。"""

    now = datetime.now(timezone.utc)  # TODO: 使用 UTC 记录使用时间
    db.execute(
        text(
            """
            UPDATE psychology_themes
            SET used = 1,
                used_at = :used_at,
                used_by_run_id = :run_id,
                locked_by_run_id = NULL,
                locked_at = NULL
            WHERE id = :theme_id
            """
        ),
        {"used_at": now.isoformat(), "run_id": run_id, "theme_id": theme_id},
    )
    db.commit()


def orchestrate_once(settings, db: Session, run_id: str) -> None:  # 定义 orchestrator 单次执行入口
    """基于软锁的单次 orchestrator 执行入口，串起领取主题与去重落库流程。"""  # 函数中文说明

    _update_run(db, run_id, "scheduled")  # 新增: 记录调度开始
    theme = lease_theme_for_run(db, run_id=run_id)  # 领取一条待生成的主题并打上软锁
    if not theme:  # 判断是否成功领取主题
        print("⚠️ 无可用主题")  # 记录提示信息
        _update_run(db, run_id, "skipped")  # 新增: 无任务直接跳过
        return  # 无主题时直接返回

    try:
        _update_run(db, run_id, "generating")  # 新增: 更新状态为生成中
        title = theme.get("psychology_definition") or f"{theme.get('psychology_keyword', '')} 心理解析"  # 使用主题定义或构造标题
        body = f"占位正文：角色={theme.get('character_name','')}, 作品={theme.get('show_name','')}, 关键词={theme.get('psychology_keyword','')}"  # 构造占位正文确保流程连通
        result = insert_article_tx(  # 调用去重与事务落库逻辑
            session=db,  # 传入当前数据库会话
            title=title,  # 指定生成的标题文本
            body=body,  # 指定生成的正文内容
            role=theme.get("character_name", ""),  # 指定角色来源
            work=theme.get("show_name", ""),  # 指定作品来源
            keyword=theme.get("psychology_keyword", ""),  # 指定心理学关键词
            lang="zh",  # 指定语言代码
            run_id=run_id,  # 传入当前运行标识
        )
        article_id = result["article_id"]  # 获取新写入文章的 ID
        print(f"✅ 写入文章 ID={article_id}")  # 输出成功日志
        _update_run(db, run_id, "prepared")  # 新增: 更新状态为已准备
        _update_run(db, run_id, "delivering")  # 新增: 更新状态为投递中
        delivery_results = deliver_article_to_all(db, settings, article_id=article_id)  # 新增: 触发平台分发
        statuses = {platform: res.status for platform, res in delivery_results.items()}  # 新增: 收集状态
        if not delivery_results:  # 新增: 无启用平台视为成功
            _update_run(db, run_id, "success")  # 新增: 直接标记成功
        elif all(status in {"prepared", "success", "skipped"} for status in statuses.values()):  # 新增: 判断成功
            _update_run(db, run_id, "success")  # 新增: 标记运行成功
        elif any(status == "failed" for status in statuses.values()):  # 新增: 存在失败时处理
            max_attempts = settings.retry_max_attempts  # 新增: 读取配置上限
            attempt_rows = db.execute(  # 新增: 查询当前尝试次数
                text(
                    """
                    SELECT platform, attempt_count
                    FROM platform_logs
                    WHERE article_id = :aid
                    """
                ),
                {"aid": article_id},
            ).mappings().all()
            attempt_map = {row["platform"]: int(row["attempt_count"] or 0) for row in attempt_rows}  # 新增: 构造映射
            failed_platforms = [p for p, s in statuses.items() if s == "failed"]  # 新增: 提取失败平台
            if failed_platforms and all(attempt_map.get(p, 0) >= max_attempts for p in failed_platforms):  # 新增: 判断是否超过上限
                _update_run(db, run_id, "failed", error=str(statuses))  # 新增: 标记彻底失败
            else:
                _update_run(db, run_id, "partial", error=str(statuses))  # 新增: 标记部分完成
        else:
            _update_run(db, run_id, "partial", error=str(statuses))  # 新增: 其他状态视为部分完成
    except Exception as exc:  # noqa: BLE001  # 捕获所有异常以便回滚软锁
        print(f"❌ 生成或落库失败: {exc}")  # 打印失败原因
        release_theme_lock(db, theme_id=theme["id"])  # 释放主题软锁避免题目被吃掉
        _update_run(db, run_id, "failed", error=str(exc))  # 新增: 记录失败状态
        raise  # 将异常继续抛出交由上层处理


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
        job_path, temp_dir, env_runtime_path = vps_job_packager.pack_job_and_env(
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
        ssh_runner.run_remote_job(temp_dir=temp_dir, env_file=env_runtime_path, command=["echo", "noop"])  # TODO: 占位调用以触发清理
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
