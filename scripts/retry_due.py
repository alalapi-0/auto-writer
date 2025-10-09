"""重试调度脚本，扫描到期 platform_logs 并触发分发。"""  # 脚本中文说明
from __future__ import annotations  # 启用未来注解语法

from datetime import datetime, timezone  # 处理时间

from sqlalchemy import text  # 执行原生 SQL

from app.delivery.dispatcher import deliver_article_to_all  # 引入分发器
from app.db.migrate import SessionLocal  # 获取数据库会话
from config.settings import settings  # 导入全局配置


def main() -> None:
    """脚本入口，查询到期的重试任务。"""  # 函数中文文档

    now = datetime.now(timezone.utc)  # 获取当前时间
    max_attempts = settings.retry_max_attempts  # 最大重试次数
    stmt = text(
        """
        SELECT DISTINCT article_id
        FROM platform_logs
        WHERE next_retry_at IS NOT NULL
          AND next_retry_at <= :now
          AND status = 'failed'
          AND attempt_count < :max_attempts
        ORDER BY next_retry_at ASC
        """
    )  # 构造查询
    with SessionLocal() as session:  # 创建会话
        rows = session.execute(stmt, {"now": now, "max_attempts": max_attempts}).fetchall()  # 执行查询
        for (article_id,) in rows:  # 遍历到期任务
            print(f"== Retry article #{article_id} ==")  # 输出提示
            try:
                results = deliver_article_to_all(session, settings, article_id)  # 调用分发
                for platform, result in results.items():  # 遍历结果
                    print(f"  - {platform}: {result.status} {result.error or ''}")  # 打印状态
            except Exception as exc:  # 捕获异常
                print(f"  ! error: {exc}")  # 输出错误


if __name__ == "__main__":  # 脚本入口
    main()  # 执行主函数
