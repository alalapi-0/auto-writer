"""测试环境通用配置。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 计算项目根目录
if str(PROJECT_ROOT) not in sys.path:  # 若根目录未加入 sys.path
    sys.path.insert(0, str(PROJECT_ROOT))  # 将根目录加入搜索路径，便于导入包
