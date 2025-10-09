# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""自检脚本入口，封装 app.cli.doctor 以供命令行调用。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from app.cli.doctor import main  # 导入自检入口


def run() -> None:  # 定义包装函数
    """执行自检并保持向后兼容的调用方式。"""  # 函数说明

    main()  # 调用核心逻辑


if __name__ == "__main__":  # 判断直接执行
    run()  # 执行包装函数
