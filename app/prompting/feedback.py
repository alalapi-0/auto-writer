"""Prompt Variant 权重调节模块，结合人工复核反馈动态调整流量分配。"""  # 中文模块说明

from __future__ import annotations  # 启用未来注解

from contextlib import contextmanager  # 构建会话上下文
from datetime import datetime, timedelta  # 处理时间运算
from typing import Dict, Iterable  # 类型提示

from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from app.db.migrate import SessionLocal  # 主库 Session 工厂
from app.db import models  # ORM 模型
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志记录器

WEIGHT_MIN = 0.2  # 权重下限，避免流量被打至零
WEIGHT_MAX = 3.0  # 权重上限，防止单一 Variant 独占
WEIGHT_STEP = 0.1  # 单次调整步长，保持“轻微”调整
COOLDOWN_SECONDS = 3600  # 冷却时间，避免频繁震荡


@contextmanager
def session_scope() -> Iterable[Session]:  # 会话上下文封装
    """提供数据库 Session，上层无需关心关闭逻辑。"""  # 中文注释

    session = SessionLocal()
    try:
        yield session  # 暴露 Session
        session.commit()  # 正常结束时提交
    except Exception:  # noqa: BLE001  # 捕获所有异常
        session.rollback()  # 出现异常回滚
        raise  # 继续抛出交由上层处理
    finally:
        session.close()  # 释放连接


def _ensure_stat(session: Session, variant: str) -> models.PromptVariantStat:  # 获取或创建权重记录
    """若不存在记录则初始化默认权重。"""  # 中文说明

    stat = (
        session.query(models.PromptVariantStat)
        .filter(models.PromptVariantStat.variant == variant)
        .one_or_none()
    )  # 查询现有记录
    if stat is None:  # 未找到则创建
        stat = models.PromptVariantStat(variant=variant, weight=1.0)
        session.add(stat)
        session.flush()  # 刷新以获得主键
    return stat  # 返回记录


def get_dynamic_weights(variants: Iterable[str]) -> Dict[str, float]:  # 读取动态权重
    """返回指定 Variant 的权重映射，若无记录则默认为 1.0。"""  # 中文说明

    result: Dict[str, float] = {}
    with session_scope() as session:  # 打开会话
        rows = (
            session.query(models.PromptVariantStat)
            .filter(models.PromptVariantStat.variant.in_(list(variants)))
            .all()
        )  # 查询所有匹配记录
        for row in rows:
            result[row.variant] = float(row.weight)
    return result  # 返回字典


def record_review_outcome(variant: str | None, outcome: str, edit_ratio: float) -> None:  # 记录人工复核结果
    """根据人工复核结果调整 Prompt Variant 权重。"""  # 中文说明

    if not variant:  # 缺少 Variant 直接忽略
        LOGGER.debug("record_review_outcome skipped due to empty variant")
        return
    normalized_ratio = max(0.0, min(1.0, float(edit_ratio or 0.0)))  # 保证幅度在 0-1
    now = datetime.utcnow()  # 当前时间
    with session_scope() as session:  # 打开事务
        stat = _ensure_stat(session, variant)  # 获取记录
        if stat.cooldown_until and stat.cooldown_until > now:  # 冷却期内
            LOGGER.debug(
                "variant %s in cooldown until %s, skip adjustment", variant, stat.cooldown_until
            )
            return  # 不进行调整

        delta = 0.0  # 初始化权重增量
        if outcome == "rejected":  # 驳回则下调
            delta = -WEIGHT_STEP
            stat.total_rejections += 1
        else:
            stat.total_approvals += 1
            if outcome == "approve_minor":  # 小幅编辑视为正反馈
                delta = WEIGHT_STEP
            elif outcome == "approve_major":  # 大幅编辑视为负反馈
                delta = -WEIGHT_STEP
            else:  # 其他情况按编辑幅度判定
                delta = WEIGHT_STEP if normalized_ratio <= 0.1 else -WEIGHT_STEP

        new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, stat.weight + delta))  # 应用上下限
        if abs(new_weight - stat.weight) > 1e-9:  # 确认确实调整
            LOGGER.info(
                "variant_weight_update",
                extra={
                    "variant": variant,
                    "outcome": outcome,
                    "ratio": normalized_ratio,
                    "from": stat.weight,
                    "to": new_weight,
                },
            )
            stat.weight = new_weight
        stat.last_feedback = now  # 更新反馈时间
        stat.cooldown_until = now + timedelta(seconds=COOLDOWN_SECONDS)  # 设置冷却
*** End of File ***
