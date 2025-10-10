"""OIDC 登录客户端与回调路由实现。"""  # 模块中文说明

from __future__ import annotations  # 启用未来注解语法

import secrets  # 生成随机 state 与 nonce
from functools import lru_cache  # 缓存远端发现文档
from typing import Any, Dict  # 类型提示别名

import httpx  # 同步 HTTP 客户端
from authlib.integrations.requests_client import OAuth2Session  # Authlib OAuth2 会话
from fastapi import APIRouter, Depends, HTTPException, Request, status  # FastAPI 组件
from fastapi.responses import HTMLResponse, RedirectResponse  # FastAPI 响应类型

from config.settings import settings  # 引入全局配置
from app.auth.security import create_access_token, hash_password  # 引入 JWT 工具与密码哈希
from app.db.migrate_sched import sched_session_scope  # 导入调度库 Session 管理器
from app.db.models_sched import User  # 导入用户模型
from app.utils.logger import get_logger  # 引入日志工具

LOGGER = get_logger(__name__)  # 初始化模块日志

router = APIRouter()  # 创建路由对象

NONCE_CACHE: Dict[str, str] = {}  # 缓存 state 对应的 nonce
CALLBACK_PATH = settings.oidc_redirect_path  # 读取配置中的回调路径


def ensure_oidc_enabled() -> None:  # 定义依赖函数校验 OIDC 开关
    """在路由处理前确认 OIDC 功能已启用。"""  # 函数中文说明

    if not settings.oidc_enable:  # 若未启用
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC disabled")  # 返回 404


@lru_cache(maxsize=1)
def _get_oidc_metadata() -> Dict[str, Any]:  # 缓存 OIDC 发现文档
    """读取并缓存 OpenID Connect 发现文档。"""  # 函数中文说明

    if not settings.oidc_issuer:  # 缺少 Issuer 配置
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC issuer missing")  # 抛出异常
    discovery_url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"  # 拼接发现文档地址
    try:  # 捕获网络异常
        response = httpx.get(discovery_url, timeout=10.0)  # 请求 OIDC 配置
        response.raise_for_status()  # 若响应错误则抛出异常
    except httpx.HTTPError as exc:  # 捕获 HTTP 异常
        LOGGER.error("拉取 OIDC 发现文档失败 url=%s error=%s", discovery_url, exc)  # 记录错误但不包含敏感信息
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC discovery failed") from exc  # 抛出 503
    return response.json()  # 返回解析后的 JSON


def build_oidc_client(redirect_uri: str) -> OAuth2Session:  # 构建 OIDC 客户端
    """基于配置创建 OAuth2Session，并加载服务器元数据。"""  # 函数中文说明

    ensure_oidc_enabled()  # 再次确认开关状态
    if not settings.oidc_client_id:  # 缺少客户端 ID 时
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC client id missing")  # 抛出异常
    metadata = _get_oidc_metadata()  # 读取发现文档
    client = OAuth2Session(  # 创建 OAuth2 会话对象
        client_id=settings.oidc_client_id,  # 配置客户端 ID
        client_secret=settings.oidc_client_secret or None,  # 配置客户端密钥，允许空值
        scope="openid email profile",  # 请求基础 scope
        redirect_uri=redirect_uri,  # 设置回调地址
    )
    client.load_server_metadata(metadata)  # 加载远端元数据方便后续解析
    return client  # 返回客户端实例


@router.get("/auth/oidc/login", name="oidc_login")
async def oidc_login(request: Request, _: None = Depends(ensure_oidc_enabled)) -> RedirectResponse:  # 登录入口路由
    """引导用户跳转到身份提供方完成授权。"""  # 函数中文说明

    redirect_uri = str(request.url_for("oidc_callback"))  # 构造完整回调地址
    client = build_oidc_client(redirect_uri)  # 初始化客户端
    metadata = _get_oidc_metadata()  # 获取远端元数据
    state = secrets.token_urlsafe(32)  # 生成随机 state
    nonce = secrets.token_urlsafe(32)  # 生成随机 nonce
    authorization_url, real_state = client.create_authorization_url(  # 构造授权地址
        metadata["authorization_endpoint"],  # 读取授权端点
        state=state,  # 传入 state
        nonce=nonce,  # 传入 nonce
    )
    NONCE_CACHE[real_state] = nonce  # 缓存 state 与 nonce 对应关系
    LOGGER.info("OIDC 发起登录 state=%s", real_state)  # 记录登录动作
    return RedirectResponse(url=authorization_url)  # 重定向到身份提供方


@router.get(CALLBACK_PATH, name="oidc_callback")
async def oidc_callback(request: Request, _: None = Depends(ensure_oidc_enabled)) -> HTMLResponse:  # 回调路由
    """处理身份提供方回调并签发本地 JWT。"""  # 函数中文说明

    state = request.query_params.get("state", "")  # 读取 state 参数
    if not state:  # 若缺少 state
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing state")  # 抛出异常
    nonce = NONCE_CACHE.pop(state, None)  # 取出对应 nonce 并删除缓存
    if nonce is None:  # 未找到 nonce
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid state")  # 抛出异常
    if "error" in request.query_params:  # 若 IdP 返回错误
        error_desc = request.query_params.get("error_description", "oidc error")  # 读取错误描述
        LOGGER.warning("OIDC 回调错误 state=%s error=%s", state, error_desc)  # 记录警告
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_desc)  # 抛出异常
    code = request.query_params.get("code")  # 读取授权码
    if not code:  # 缺少授权码
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing code")  # 抛出异常
    redirect_uri = str(request.url_for("oidc_callback"))  # 重新构造回调地址
    client = build_oidc_client(redirect_uri)  # 初始化客户端
    metadata = _get_oidc_metadata()  # 获取元数据
    try:  # 捕获令牌交换异常
        token = client.fetch_token(  # 通过授权码换取令牌
            metadata["token_endpoint"],  # 指定令牌端点
            code=code,  # 提供授权码
        )
    except Exception as exc:  # noqa: BLE001  # 捕获 Authlib 抛出的任意异常
        LOGGER.error("OIDC 换取令牌失败 state=%s error=%s", state, exc)  # 记录错误
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token exchange failed") from exc  # 抛出异常
    try:  # 捕获 ID Token 解析异常
        claims = client.parse_id_token(token, nonce=nonce)  # 验证并解析 ID Token
    except Exception as exc:  # noqa: BLE001  # 捕获解析异常
        LOGGER.error("OIDC 解析 ID Token 失败 state=%s error=%s", state, exc)  # 记录错误
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid id_token") from exc  # 抛出异常
    email = claims.get("email")  # 读取邮箱
    subject = claims.get("sub")  # 读取主体标识
    display_name = claims.get("name")  # 读取名称
    username = email or subject  # 选择用户名优先使用邮箱
    if not username:  # 若仍缺少唯一标识
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing user identifier")  # 抛出异常
    with sched_session_scope() as session:  # 打开数据库会话
        user = session.query(User).filter(User.username == username).one_or_none()  # 查询现有用户
        if user is None:  # 若首次登录
            if not settings.oidc_auto_create_viewer:  # 未开启自动创建
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user not provisioned")  # 拒绝登录
            random_password = secrets.token_urlsafe(18)  # 生成随机密码占位
            user = User(  # 构建新用户对象
                username=username,  # 设置用户名
                password_hash=hash_password(random_password),  # 生成密码哈希
                role="viewer",  # 默认 viewer 权限
                is_active=True,  # 标记为启用
            )
            session.add(user)  # 添加到会话
            session.flush()  # 刷新以获取 ID
            LOGGER.info("OIDC 自动创建 viewer 用户 username=%s", username)  # 记录创建事件
        else:  # 已存在用户
            if not user.is_active:  # 若用户被禁用
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")  # 拒绝登录
    token_value = create_access_token(subject=user.username, role=user.role)  # 创建本地 JWT
    LOGGER.info("OIDC 登录成功 username=%s role=%s", user.username, user.role)  # 记录成功日志
    html_content = """
<!DOCTYPE html>
<html lang=\"zh\">
<head>
  <meta charset=\"utf-8\" />
  <title>登录成功</title>
</head>
<body>
  <script>
    localStorage.setItem('jwt', '%s');
    localStorage.setItem('oidc_name', %s);
    window.location.href = '/';
  </script>
</body>
</html>
""" % (token_value, repr(display_name or username))  # 构造写入 token 的页面
    return HTMLResponse(content=html_content)  # 返回 HTML 响应
