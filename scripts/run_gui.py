# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""AutoWriter GUI 启动脚本，封装命令行入口。"""  # 模块说明

from __future__ import annotations  # 启用未来注解

from app.gui.main import main  # 导入 GUI 主入口


if __name__ == "__main__":  # 允许脚本直接执行
    main()  # 调用主入口
