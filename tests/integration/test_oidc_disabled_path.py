# -*- coding: utf-8 -*-  # 指定 UTF-8 编码
"""验证 OIDC 关闭时相关路由返回 404。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import pytest  # 导入 pytest 以便条件跳过

pytest.importorskip("fastapi")  # 若未安装 FastAPI 则跳过整个模块
from fastapi.testclient import TestClient  # 导入 FastAPI 测试客户端

from app.dashboard import server as server_module  # 导入 Dashboard 服务模块
from config.settings import settings  # 引入配置对象以获取回调路径


def test_oidc_login_route_disabled() -> None:  # 测试 OIDC 登录入口关闭
    """当 OIDC 未启用时，登录入口应返回 404。"""  # 测试用例说明

    client = TestClient(server_module.app)  # 创建测试客户端
    response = client.get("/auth/oidc/login")  # 请求 OIDC 登录地址
    assert response.status_code == 404  # 断言返回 404


def test_oidc_callback_route_disabled() -> None:  # 测试 OIDC 回调地址关闭
    """当 OIDC 未启用时，回调地址应返回 404。"""  # 测试用例说明

    client = TestClient(server_module.app)  # 创建测试客户端
    response = client.get(settings.oidc_redirect_path)  # 请求配置中的回调路径
    assert response.status_code == 404  # 断言返回 404
