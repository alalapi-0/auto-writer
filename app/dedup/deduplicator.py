"""去重策略模块，实现签名唯一、组合唯一以及 SimHash 相似度三道闸机制。"""  # 模块中文文档说明
from __future__ import annotations  # 引入未来注解语法以保持类型提示兼容性
from dataclasses import dataclass  # 引入数据类用于封装配置
from datetime import datetime, timedelta  # 导入时间工具用于窗口判断
from typing import Optional, Tuple, Dict, Any  # 导入类型提示以增强可读性
from sqlalchemy import text  # 导入 SQL 构造器用于执行原生查询
from sqlalchemy.orm import Session  # 引入 SQLAlchemy 会话类型
from app.dedup.textnorm import (  # 从文本归一化模块导入签名与工具函数
    title_signature,
    content_signature,
    simhash,
    hamming_distance,
    normalize_text,
)  # 保持中文注释行内说明

@dataclass  # 使用数据类简化配置定义
class DedupConfig:  # 定义去重配置数据结构
    """去重参数配置，包含 SimHash 阈值及组合窗口。"""  # 数据类中文文档
    simhash_bits: int = 64  # SimHash 位数
    simhash_hamming_threshold: int = 3  # 汉明距离阈值，越小越严格
    day_window: int = 1  # 组合唯一检查的日粒度窗口
    recent_limit: int = 200  # 相似度扫描时读取的历史文章数量上限

def normalize_entities(role: str, work: str, keyword: str, lang: str = "zh") -> Tuple[str, str, str, str]:  # 定义实体归一化函数
    """对角色、作品、关键词及语言进行归一化处理。"""  # 函数中文文档说明
    normalized_role = normalize_text(role)  # 归一化角色名称
    normalized_work = normalize_text(work)  # 归一化作品名称
    normalized_keyword = normalize_text(keyword)  # 归一化心理学关键词
    normalized_lang = (lang or "zh").lower()  # 语言代码统一为小写
    return normalized_role, normalized_work, normalized_keyword, normalized_lang  # 返回归一化结果元组

def precheck_by_combo(session: Session, role_slug: str, work_slug: str, psych_keyword: str, lang: str, now: datetime, cfg: DedupConfig) -> bool:  # 定义组合唯一性检查函数
    """检查同一窗口内角色、作品、关键词和语言组合是否已存在。"""  # 函数中文文档
    start_date = (now - timedelta(days=cfg.day_window - 1)).date()  # 计算窗口起始日期
    end_date = now.date()  # 计算窗口结束日期
    query = text(
        """
        SELECT 1
        FROM articles
        WHERE role_slug = :role_slug
          AND work_slug = :work_slug
          AND psych_keyword = :psych_keyword
          AND lang = :lang
          AND date(created_at) BETWEEN :start_date AND :end_date
        LIMIT 1
        """
    )  # 构造组合唯一查询 SQL
    result = session.execute(
        query,
        {
            "role_slug": role_slug,
            "work_slug": work_slug,
            "psych_keyword": psych_keyword,
            "lang": lang,
            "start_date": start_date,
            "end_date": end_date,
        },
    ).first()  # 执行查询并返回首条记录
    return result is not None  # 若存在记录则表示组合冲突

def precheck_by_content_sig(session: Session, content_sig: str) -> bool:  # 定义正文签名检查函数
    """检查正文签名是否已存在以阻止完全重复文章。"""  # 函数中文文档
    query = text("SELECT 1 FROM articles WHERE content_signature = :sig LIMIT 1")  # 构造签名唯一查询
    result = session.execute(query, {"sig": content_sig}).first()  # 执行查询
    return result is not None  # 返回是否检测到重复

def precheck_by_simhash(session: Session, body: str, cfg: DedupConfig) -> Optional[Dict[str, Any]]:  # 定义近似重复检查函数
    """基于 SimHash 的近似重复检查，返回疑似重复的文章信息。"""  # 函数中文文档
    target_hash = simhash(body, bits=cfg.simhash_bits)  # 计算待检测正文的 SimHash
    query = text(
        """
        SELECT id, content_signature
        FROM articles
        WHERE content_signature IS NOT NULL
        ORDER BY id DESC
        LIMIT :limit
        """
    )  # 构造获取最近文章签名的 SQL
    rows = session.execute(query, {"limit": cfg.recent_limit}).mappings().all()  # 查询最近若干条文章
    for row in rows:  # 遍历历史记录
        signature = row.get("content_signature", "")  # 读取历史签名
        if not signature:  # 若为空则跳过
            continue  # 继续下一条
        try:
            simhash_hex = signature.split("-")[-1]  # 提取签名中的 SimHash 部分
            other_hash = int(simhash_hex, 16)  # 将十六进制转换为整数
        except ValueError:
            continue  # 若解析失败则跳过该记录
        distance = hamming_distance(target_hash, other_hash)  # 计算汉明距离
        if distance <= cfg.simhash_hamming_threshold:  # 判断是否在相似阈值内
            return {"id": row["id"], "content_signature": signature, "distance": distance}  # 返回疑似重复信息
    return None  # 未命中相似文章返回空值

def decide_dedup(session: Session, title: str, body: str, role: str, work: str, keyword: str, lang: str, now: datetime, cfg: DedupConfig) -> Dict[str, Any]:  # 定义综合去重判定函数
    """整合三道闸逻辑并返回包含签名与检测结果的字典。"""  # 函数中文文档
    title_sig = title_signature(title)  # 计算标题签名
    content_sig = content_signature(body)  # 计算正文签名
    role_slug, work_slug, psych_keyword, normalized_lang = normalize_entities(role, work, keyword, lang)  # 归一化实体
    combo_conflict = precheck_by_combo(session, role_slug, work_slug, psych_keyword, normalized_lang, now, cfg)  # 检查组合冲突
    signature_conflict = precheck_by_content_sig(session, content_sig)  # 检查签名冲突
    near_duplicate = precheck_by_simhash(session, body, cfg)  # 检测近似重复
    return {
        "title_signature": title_sig,
        "content_signature": content_sig,
        "role_slug": role_slug,
        "work_slug": work_slug,
        "psych_keyword": psych_keyword,
        "lang": normalized_lang,
        "combo_conflict": combo_conflict,
        "signature_conflict": signature_conflict,
        "near_duplicate": near_duplicate,
    }  # 返回综合判定结果
