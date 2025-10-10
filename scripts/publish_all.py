"""命令行入口：批量投递 outbox 草稿。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法

import argparse  # 参数解析
import sys  # 控制退出码

from app.automation.publisher import publish_all  # 批量投递函数
from app.db.migrate import SessionLocal  # 数据库会话工厂
from config.settings import get_settings  # 配置加载


def parse_args() -> argparse.Namespace:  # 构建解析器
    """解析命令行参数。"""  # 中文说明

    parser = argparse.ArgumentParser(description="批量投递 outbox 草稿")  # 初始化解析器
    parser.add_argument("--day", help="指定日期目录，格式 yyyyMMdd，可选")  # 日期参数
    parser.add_argument("--platforms", help="逗号分隔的平台列表，默认全部")  # 平台列表
    parser.add_argument("--headful", action="store_true", help="以有头模式运行浏览器")  # 是否开窗
    return parser.parse_args()  # 返回解析结果


def main() -> int:  # 主函数
    """执行批量投递并输出统计。"""  # 中文说明

    args = parse_args()  # 解析参数
    settings = get_settings()  # 加载配置
    if args.headful:  # 若要求开窗
        settings.playwright_headless = False  # 切换到有头模式
    platforms = None  # 默认平台列表
    if args.platforms:  # 若用户指定
        platforms = [item.strip() for item in args.platforms.split(",") if item.strip()]  # 拆分列表
    try:  # 捕获执行异常
        with SessionLocal() as session:  # 打开数据库会话
            summary = publish_all(  # 执行批量投递
                session,
                settings,
                day=args.day,
                platforms=platforms,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"批量投递失败: {exc}")  # 输出错误
        return 1  # 返回失败码
    print("==== 批量投递结果 ====")  # 标题
    print(f"日期: {summary['day']}")  # 日期
    print(f"平台: {', '.join(summary['platforms'])}")  # 平台列表
    print(f"总数: {len(summary['results'])}")  # 总数
    print(f"成功: {summary['success']}")  # 成功数量
    print(f"失败: {summary['failed']}")  # 失败数量
    print(f"平均耗时: {summary['average_duration']:.2f}s")  # 平均耗时
    print(f"总耗时: {summary['duration']:.2f}s")  # 总耗时
    if summary["screenshots"]:  # 若有失败截图
        print("失败截图:")  # 提示
        for path in summary["screenshots"]:  # 遍历截图
            print(f" - {path}")  # 打印路径
    else:
        print("无失败截图")  # 无截图
    print(f"整体状态: {summary['status']}")  # 总体状态
    return 0 if summary["failed"] == 0 else 1  # 根据失败数决定退出码


if __name__ == "__main__":  # 脚本入口
    sys.exit(main())  # 执行主函数
