# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""报表导出脚本，提供命令行参数控制统计窗口。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

import argparse  # 解析命令行参数

from app.observability.report import generate_report  # 导入报表生成函数
from app.utils.logger import get_logger  # 日志模块

LOGGER = get_logger(__name__)  # 初始化脚本日志


def main() -> None:  # 定义命令行入口
    """解析参数并执行报表导出。"""  # 函数说明

    parser = argparse.ArgumentParser(description="AutoWriter 报表导出")  # 构建解析器
    parser.add_argument("--window", type=int, default=7, help="统计窗口天数，默认 7")  # 添加窗口参数
    args = parser.parse_args()  # 解析参数
    LOGGER.info("export_report_start window=%s", args.window)  # 记录开始
    result = generate_report(window_days=args.window)  # 调用报表生成
    LOGGER.info("export_report_finish json=%s csv=%s", str(result["json"]), str(result["csv"]))  # 记录完成


if __name__ == "__main__":  # 判断直接执行
    main()  # 调用入口
