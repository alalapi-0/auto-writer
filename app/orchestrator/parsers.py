"""解析 VPS 回传结果并落库的工具函数。"""

from __future__ import annotations  # 启用未来注解语法

import json  # 读取 JSON 文本
from datetime import datetime  # 获取当前时间戳
from pathlib import Path  # 处理文件路径
from typing import List  # 类型提示

from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from app.db import models  # 导入 ORM 模型
from app.growth.enricher import enrich_keywords  # 引入事后补词逻辑


def load_result_json(path: Path) -> dict:
    """从文件读取 result.json。"""

    return json.loads(path.read_text(encoding="utf-8"))  # 解析 JSON


def parse_worker_log(path: Path) -> List[str]:
    """读取 worker 文本日志并按行返回。"""

    if not path.exists():  # 若日志不存在
        return []  # 返回空列表
    return path.read_text(encoding="utf-8").splitlines()  # 按行拆分


def persist_results(session: Session, run: models.Run, result: dict) -> List[str]:
    """将 result.json 数据写入本地数据库。"""

    consumed_keywords: List[str] = []  # 记录已使用的关键词
    now = datetime.utcnow()  # 获取当前时间
    articles = result.get("articles", [])  # 提取文章列表
    for article_payload in articles:  # 遍历每篇文章
        draft = models.ArticleDraft(  # 构造草稿记录
            run_id=run.id,
            character_name=article_payload.get("character_name", ""),
            work=article_payload.get("work", ""),
            keyword=article_payload.get("keyword", ""),
            title=article_payload.get("title"),
            status=article_payload.get("status", "unknown"),
            content=article_payload.get("content"),
        )
        session.add(draft)  # 写入草稿
        session.flush()  # 刷新以获得草稿 ID

        for platform_result in article_payload.get("platform_results", []):  # 处理平台投递日志
            log = models.PlatformLog(
                article_id=draft.id,
                platform=platform_result.get("platform", "unknown"),
                ok=bool(platform_result.get("ok", False)),
                id_or_url=platform_result.get("id_or_url"),
                error=platform_result.get("error"),
            )
            session.add(log)  # 写入平台日志

        used_pair = models.UsedPair(  # 构造 used_pairs 记录
            character_name=draft.character_name,
            work=draft.work,
            keyword=draft.keyword,
            run_id=run.run_id,
            used_on=run.run_date,
            similarity_hash=None,  # TODO: 接入语义哈希比对
        )
        session.add(used_pair)  # 写入 used_pairs

        keyword_record = (
            session.query(models.Keyword)
            .filter(models.Keyword.keyword == draft.keyword)
            .one_or_none()
        )  # 查询关键词记录
        if keyword_record:
            keyword_record.last_used_at = now  # 更新最近使用时间
            keyword_record.usage_count += 1  # 累加使用次数
        consumed_keywords.append(draft.keyword)  # 记录已消耗关键词

    run.status = "success" if result.get("success") else "failed"  # 更新运行状态
    run.keywords_consumed = len(consumed_keywords)  # 更新消耗计数
    session.commit()  # 提交事务
    return consumed_keywords  # 返回消耗的关键词列表


def perform_postrun_enrich(
    session: Session,
    run: models.Run,
    consumed_keywords: List[str],
    group_size: int,
) -> List[str]:
    """执行“每消耗 3 个补 3 个”的补词策略。"""

    if not consumed_keywords:  # 若无关键词被消耗
        return []  # 直接返回空列表
    new_keywords = enrich_keywords(consumed_keywords, group_size)  # 生成补充关键词
    created: List[str] = []  # 记录实际写入的关键词
    for keyword in new_keywords:  # 遍历候选关键词
        exists = (
            session.query(models.Keyword)
            .filter(models.Keyword.keyword == keyword)
            .first()
        )  # 判断是否已存在
        if exists:
            continue  # 若已存在则跳过
        session.add(models.Keyword(keyword=keyword, category="enrich"))  # 写入新关键词
        created.append(keyword)  # 记录新增
    if created:
        run.keywords_added += len(created)  # 更新 run 表统计
    session.commit()  # 提交事务
    return created  # 返回新增关键词
