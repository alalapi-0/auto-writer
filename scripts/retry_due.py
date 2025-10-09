"""重试调度脚本，扫描到期 platform_logs 并触发分发。"""  # 脚本中文说明
from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import sys  # 控制退出码
from datetime import datetime, timezone  # 处理时间

from sqlalchemy import text  # 执行原生 SQL

from app.delivery.dispatcher import deliver_article_to_all  # 引入分发器
from app.db.migrate import SessionLocal  # 获取数据库会话
from app.utils.logger import get_logger  # 统一日志模块
from config.settings import settings  # 导入全局配置

LOGGER = get_logger(__name__)  # 初始化脚本日志


def main() -> None:
    """脚本入口，查询到期的重试任务。"""  # 函数中文文档

    parser = argparse.ArgumentParser(description="retry due platform deliveries")  # 创建解析器
    parser.add_argument("--limit", type=int, default=10, help="本次最多处理的文章数")  # 添加限制参数
    args = parser.parse_args()  # 解析参数
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
        LIMIT :limit
        """
    )  # 构造查询
    try:  # 捕获运行异常
        with SessionLocal() as session:  # 创建会话
            rows = session.execute(
                stmt,
                {"now": now, "max_attempts": max_attempts, "limit": max(1, args.limit)},
            ).fetchall()  # 执行查询
            if not rows:  # 若无待重试任务
                print("⚠️ 无到期重试任务")  # 输出提示
                LOGGER.info("retry_due_empty")  # 记录日志
                return  # 结束执行
            for (article_id,) in rows:  # 遍历到期任务
                LOGGER.info("retry_start article_id=%s", article_id)  # 记录开始
                print(f"== 重试文章 {article_id} ==")  # 输出提示
                results = deliver_article_to_all(session, settings, article_id)  # 调用分发
                for platform, result in results.items():  # 遍历结果
                    icon = "✅" if result.status in {"prepared", "success"} else "⚠️"  # 选择图标
                    if result.status == "failed":  # 失败状态
                        icon = "❌"  # 设置失败图标
                    print(f"{icon} {platform}: {result.status} {result.error or ''}")  # 打印状态
                LOGGER.info("retry_finish article_id=%s", article_id)  # 记录完成
    except Exception as exc:  # 捕获异常
        LOGGER.exception("retry_due_failed error=%s", str(exc))  # 记录异常
        print(f"❌ 重试流程失败: {exc}")  # 输出错误
        sys.exit(1)  # 非零退出


if __name__ == "__main__":  # 脚本入口
    main()  # 执行主函数
