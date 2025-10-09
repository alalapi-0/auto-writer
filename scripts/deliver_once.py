"""离线触发平台分发，生成最小可用草稿制品。"""  # 脚本中文说明
from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import sys  # 控制退出码
from typing import List  # 类型提示

from sqlalchemy import text  # 执行原生 SQL
from sqlalchemy.orm import Session  # 会话类型

from app.delivery.dispatcher import deliver_article_to_all  # 引入分发器
from app.db.migrate import SessionLocal  # 获取 Session 工厂
from app.utils.logger import get_logger  # 统一日志模块
from config.settings import settings  # 导入全局配置

LOGGER = get_logger(__name__)  # 初始化脚本日志记录器


def _fetch_recent_article_ids(session: Session, limit: int) -> List[int]:
    """查询最近创建的文章 ID 列表。"""  # 函数中文文档

    stmt = text(
        """
        SELECT id
        FROM articles
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )  # 构造查询
    with session.begin():  # 开启事务确保读一致
        rows = session.execute(stmt, {"limit": limit}).fetchall()  # 执行查询
    return [row[0] for row in rows]  # 返回 ID 列表


def main() -> None:
    """脚本入口，支持单篇或批量触发分发。"""  # 函数中文文档

    parser = argparse.ArgumentParser(description="deliver article drafts")  # 创建解析器
    parser.add_argument("--article-id", type=int, help="指定文章 ID")  # 可选单篇 ID
    parser.add_argument("--limit", type=int, default=3, help="缺省处理最近 N 篇")  # 批量数量
    args = parser.parse_args()  # 解析参数

    try:  # 捕获运行异常
        with SessionLocal() as session:  # 管理数据库会话
            ids = [args.article_id] if args.article_id else _fetch_recent_article_ids(session, max(1, args.limit))  # 选择目标
            if not ids:  # 若无文章
                print("⚠️ 未找到可投递的文章")  # 输出提示
                LOGGER.warning("deliver_none_found")  # 记录日志
                return  # 结束执行
            for article_id in ids:  # 遍历文章
                LOGGER.info("deliver_start article_id=%s", article_id)  # 记录开始
                print(f"== 文章 {article_id} 投递 ==")  # 输出提示
                results = deliver_article_to_all(session, settings, article_id)  # 调用分发
                if not results:  # 无启用平台
                    print("⚠️ 未启用平台，跳过")  # 输出提示
                    LOGGER.warning("deliver_no_platform article_id=%s", article_id)  # 记录日志
                    continue  # 下一个
                for platform, result in results.items():  # 遍历结果
                    icon = "✅" if result.status in {"prepared", "success"} else "⚠️"  # 根据状态选择图标
                    if result.status == "failed":  # 失败使用红色图标
                        icon = "❌"  # 设置失败图标
                    print(f"{icon} {platform}: {result.status} {result.error or ''}")  # 输出状态
                LOGGER.info("deliver_finish article_id=%s", article_id)  # 记录完成
    except Exception as exc:  # 捕获异常
        LOGGER.exception("deliver_once_failed error=%s", str(exc))  # 记录异常
        print(f"❌ 投递失败: {exc}")  # 输出错误
        sys.exit(1)  # 返回非零退出码
if __name__ == "__main__":  # 脚本入口
    main()  # 执行主函数
