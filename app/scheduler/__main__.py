"""允许通过 `python -m app.scheduler` 启动调度服务。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from .service import main  # 导入主函数

if __name__ == "__main__":  # 判断运行方式
    main()  # 调用入口
