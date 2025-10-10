"""解析 VPS 回传结果并落库的工具函数。"""

from __future__ import annotations  # 启用未来注解语法

import json  # 读取 JSON 文本
import random  # 随机抽检使用
from datetime import datetime  # 获取当前时间戳
from pathlib import Path  # 处理文件路径
from typing import List  # 类型提示

from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from config.settings import settings  # 读取配置项
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
        tags_raw = article_payload.get("tags")  # 读取标签原始值
        if isinstance(tags_raw, str):  # 字符串按逗号拆分
            tags_value = [item.strip() for item in tags_raw.split(",") if item.strip()]
        elif isinstance(tags_raw, list):  # 已经是列表直接使用
            tags_value = tags_raw
        else:
            tags_value = None  # 其他类型一律忽略

        draft = models.ArticleDraft(  # 构造草稿记录
            run_id=run.id,
            character_name=article_payload.get("character_name", ""),
            work=article_payload.get("work", ""),
            keyword=article_payload.get("keyword", ""),
            title=article_payload.get("title"),
            status=article_payload.get("status", "unknown"),
            summary=article_payload.get("summary"),
            tags=tags_value,
            content=article_payload.get("content"),
        )
        session.add(draft)  # 写入草稿
        session.flush()  # 刷新以获得草稿 ID

        audit_payload = article_payload.get("quality_audit") or {}  # 读取质量审计信息
        audit_record = None  # 预留变量，用于后续更新人工复核状态
        for platform_result in article_payload.get("platform_results", []):  # 处理平台投递日志
            log = models.PlatformLog(
                article_id=draft.id,
                platform=platform_result.get("platform", "unknown"),
                target_id=platform_result.get("id_or_url"),  # 新增: 记录平台草稿 ID
                status="success" if platform_result.get("ok") else "failed",  # 新增: 同步状态字段
                ok=bool(platform_result.get("ok", False)),
                id_or_url=platform_result.get("id_or_url"),
                error=platform_result.get("error"),
                attempt_count=1,  # 新增: 默认首轮尝试次数
                last_error=platform_result.get("error"),  # 新增: 同步最近错误
                prompt_variant=platform_result.get("variant")
                or article_payload.get("prompt_variant")
                or audit_payload.get("variant"),  # 新增: 记录 Prompt 版本
                payload=platform_result,  # 新增: 存档原始返回数据
            )
            session.add(log)  # 写入平台日志

        if audit_payload:  # 当存在质量闸门信息时写入审计表
            audit_record = models.ContentAudit(
                article_id=draft.id,
                prompt_variant=audit_payload.get("variant"),
                scores=audit_payload.get("scores") or {},
                reasons=audit_payload.get("reasons") or [],
                attempts=audit_payload.get("attempts") or [],
                passed=bool(audit_payload.get("passed")),
                fallback_count=int(audit_payload.get("fallback_count") or 0),
                manual_review=bool(article_payload.get("manual_review")),
            )
            session.add(audit_record)

        passed = bool(audit_payload.get("passed"))  # 读取质量闸门是否通过
        needs_review = False  # 默认不进入人工复核
        reason = "sampling"  # 默认原因
        if not passed:  # 闸门失败强制入队
            needs_review = True
            reason = "guard_failed"
        elif settings.qa_sampling_rate > 0 and random.random() < settings.qa_sampling_rate:  # 按比例抽检
            needs_review = True
            reason = "sampling"

        if needs_review:  # 需要进入复核队列
            queue_item = models.ReviewQueue(
                draft_id=draft.id,
                reason=reason,
                status="pending",
            )
            session.add(queue_item)
            draft.status = "pending_review"  # 更新草稿状态为待复核
            if audit_record is not None:  # 标记审计记录进入人工复核
                audit_record.manual_review = True

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
