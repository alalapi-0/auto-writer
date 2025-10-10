"""命令行入口：投递单篇草稿到指定平台。"""  # 模块中文文档
from __future__ import annotations  # 启用未来注解语法

import argparse  # 解析命令行参数
import sys  # 控制退出码
from pprint import pprint  # 美化输出

from app.automation.publisher import publish_one  # 调用投递逻辑
from app.db.migrate import SessionLocal  # 数据库会话工厂
from config.settings import get_settings  # 读取配置


def parse_args() -> argparse.Namespace:  # 构建参数解析器
    """构建命令行参数并解析。"""  # 中文说明

    parser = argparse.ArgumentParser(description="使用 Playwright 投递单篇草稿")  # 初始化解析器
    parser.add_argument("--platform", required=True, choices=["wechat_mp", "zhihu"], help="目标平台")  # 目标平台
    parser.add_argument("--title", required=True, help="草稿标题，需与 outbox 文件夹一致")  # 标题参数
    parser.add_argument("--day", help="草稿所在日期目录，格式 yyyyMMdd，可选")  # 日期目录
    parser.add_argument("--headful", action="store_true", help="以有头模式运行浏览器，便于扫码")  # 是否无头
    return parser.parse_args()  # 返回解析结果


def main() -> int:  # 主函数
    """执行投递流程并返回退出码。"""  # 中文说明

    args = parse_args()  # 解析参数
    settings = get_settings()  # 读取默认配置
    if args.headful:  # 若要求开窗
        settings.playwright_headless = False  # 改为有头模式
    try:  # 捕获投递异常
        with SessionLocal() as session:  # 打开数据库会话
            result = publish_one(  # 调用投递函数
                session,
                settings,
                platform=args.platform,
                title=args.title,
                day=args.day,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"投递失败: {exc}")  # 输出错误
        return 1  # 返回失败码
    payload_preview = result.payload.copy() if isinstance(result.payload, dict) else result.payload  # 拷贝 payload
    if isinstance(payload_preview, dict) and payload_preview.get("meta"):  # 若存在 meta
        payload_preview["meta"] = "..."  # 避免在终端展开
    pprint(  # 打印结果摘要
        {
            "platform": result.platform,
            "status": result.status,
            "target_id": result.target_id,
            "out_dir": result.out_dir,
            "payload": payload_preview,
            "error": result.error,
        }
    )
    return 0 if result.status == "success" else 1  # 根据状态返回退出码


if __name__ == "__main__":  # 脚本入口
    sys.exit(main())  # 执行主函数并退出
