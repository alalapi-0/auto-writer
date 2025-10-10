"""生成结果持久化模块，负责调用去重并以事务方式写入数据库。"""  # 模块中文说明
from __future__ import annotations  # 引入未来注解语法保证类型提示兼容
from datetime import datetime, timezone  # 导入时间函数用于生成时间戳
from typing import Any, Dict, Optional  # 引入类型提示增强可读性
from sqlalchemy import text  # 导入 SQL 构造器用于执行原生语句
from sqlalchemy.orm import Session  # 引入 SQLAlchemy 会话类型
from app.dedup.deduplicator import decide_dedup, DedupConfig  # 导入去重判定逻辑与配置
from app.chaos.hooks import maybe_inject_chaos  # 引入混沌注入钩子


def insert_article_tx(session: Session, title: str, body: str, role: str, work: str, keyword: str, lang: str = "zh", run_id: Optional[str] = None) -> Dict[str, Any]:  # 定义事务性插入函数
    """执行去重判定并在单个事务内写入 articles 与 used_pairs。"""  # 函数中文文档
    maybe_inject_chaos("generation.persist")  # 持久化阶段触发混沌演练
    now = datetime.now(timezone.utc)  # 获取当前 UTC 时间
    cfg = DedupConfig()  # 初始化默认去重配置
    verdict = decide_dedup(session, title, body, role, work, keyword, lang, now, cfg)  # 执行去重判定
    if verdict["combo_conflict"]:  # 判断组合是否冲突
        raise ValueError("DUP_COMBO_DAY: 同日相同角色作品关键词组合已存在")  # 抛出明确错误提示
    if verdict["signature_conflict"]:  # 判断签名是否冲突
        raise ValueError("DUP_CONTENT_SIG: 正文签名重复")  # 抛出签名冲突异常
    if verdict["near_duplicate"]:  # 判断近似重复
        near = verdict["near_duplicate"]  # 读取近似信息
        raise ValueError(f"DUP_NEAR: 与文章#{near['id']} 相似度过高")  # 抛出近似重复异常
    transaction = session.begin()  # 显式开启事务以便手动提交或回滚
    try:
        insert_article_sql = text(
            """
            INSERT INTO articles (
                run_id,
                character_name,
                work,
                keyword,
                title,
                status,
                content,
                role_slug,
                work_slug,
                psych_keyword,
                lang,
                title_signature,
                content_signature,
                created_at,
                meta
            )
            VALUES (
                :run_id,
                :character_name,
                :work,
                :keyword,
                :title,
                :status,
                :content,
                :role_slug,
                :work_slug,
                :psych_keyword,
                :lang,
                :title_signature,
                :content_signature,
                :created_at,
                :meta
            )
            """
        )  # 构造插入文章的 SQL 语句
        insert_params = {
            "run_id": run_id,
            "character_name": role,
            "work": work,
            "keyword": keyword,
            "title": title,
            "status": "draft",
            "content": body,
            "role_slug": verdict["role_slug"],
            "work_slug": verdict["work_slug"],
            "psych_keyword": verdict["psych_keyword"],
            "lang": verdict["lang"],
            "title_signature": verdict["title_signature"],
            "content_signature": verdict["content_signature"],
            "created_at": now,
            "meta": "{}",
        }  # 组装文章插入参数
        result = session.execute(insert_article_sql, insert_params)  # 执行文章插入
        article_id = result.lastrowid  # 获取新插入文章的主键 ID
        if article_id is None:  # 若数据库未返回主键
            article_id = session.execute(text("SELECT last_insert_rowid()"))  # 退回到 SQLite 专用查询
            article_id = article_id.scalar_one()  # 提取主键值
        simhash_tail = verdict["content_signature"].split("-")[-1] if verdict["content_signature"] else None  # 提取 SimHash 片段
        insert_used_sql = text(
            """
            INSERT INTO used_pairs (
                character_name,
                work,
                keyword,
                run_id,
                used_on,
                similarity_hash,
                role_slug,
                work_slug,
                psych_keyword,
                lang,
                first_used_at,
                last_used_at
            )
            VALUES (
                :character_name,
                :work,
                :keyword,
                :run_id,
                :used_on,
                :similarity_hash,
                :role_slug,
                :work_slug,
                :psych_keyword,
                :lang,
                :first_used_at,
                :last_used_at
            )
            ON CONFLICT(role_slug, work_slug, psych_keyword, lang)
            DO UPDATE SET
                last_used_at = excluded.last_used_at,
                used_on = excluded.used_on,
                run_id = excluded.run_id
            """
        )  # 构造写入 used_pairs 的 UPSERT 语句
        session.execute(
            insert_used_sql,
            {
                "character_name": role,
                "work": work,
                "keyword": keyword,
                "run_id": run_id or "ad_hoc",
                "used_on": now.date(),
                "similarity_hash": simhash_tail,
                "role_slug": verdict["role_slug"],
                "work_slug": verdict["work_slug"],
                "psych_keyword": verdict["psych_keyword"],
                "lang": verdict["lang"],
                "first_used_at": now,
                "last_used_at": now,
            },
        )  # 执行 used_pairs 写入或更新
        transaction.commit()  # 写入成功后提交事务
        return {"article_id": article_id, "verdict": verdict}  # 返回文章 ID 与判定信息
    except Exception:
        transaction.rollback()  # 发生异常时回滚事务
        raise  # 将异常继续抛出给上层处理
