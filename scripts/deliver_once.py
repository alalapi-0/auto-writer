"""离线触发平台分发，生成最小可用草稿制品。"""  # 脚本中文说明
from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
from typing import List  # 类型提示

from sqlalchemy import text  # 执行原生 SQL
from sqlalchemy.orm import Session  # 会话类型

from app.delivery.dispatcher import deliver_article_to_all  # 引入分发器
from app.db.migrate import SessionLocal  # 获取 Session 工厂
from config.settings import settings  # 导入全局配置


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
    rows = session.execute(stmt, {"limit": limit}).fetchall()  # 执行查询
    return [row[0] for row in rows]  # 返回 ID 列表


def main() -> None:
    """脚本入口，支持单篇或批量触发分发。"""  # 函数中文文档

    parser = argparse.ArgumentParser(description="deliver article drafts")  # 创建解析器
    parser.add_argument("--article-id", type=int, help="指定文章 ID")  # 可选单篇 ID
    parser.add_argument("--limit", type=int, default=3, help="缺省处理最近 N 篇")  # 批量数量
    args = parser.parse_args()  # 解析参数

    with SessionLocal() as session:  # 管理数据库会话
        ids = [args.article_id] if args.article_id else _fetch_recent_article_ids(session, max(1, args.limit))  # 选择目标
        for article_id in ids:  # 遍历文章
            print(f"== Deliver article #{article_id} ==")  # 输出提示
            try:
                results = deliver_article_to_all(session, settings, article_id)  # 调用分发
                if not results:  # 无启用平台
                    print("  (no enabled platforms)")  # 输出提示
                for platform, result in results.items():  # 遍历结果
                    print(f"  - {platform}: {result.status} {result.error or ''}")  # 打印状态
            except Exception as exc:  # 捕获异常
                print(f"  ! error: {exc}")  # 输出错误
if __name__ == "__main__":  # 脚本入口
    main()  # 执行主函数
