"""Dashboard 鉴权与密码工具模块。"""  # 模块说明

from __future__ import annotations  # 启用未来注解语法

from dataclasses import dataclass  # 使用 dataclass 表示用户主体
from datetime import datetime, timedelta  # 处理时间
from typing import Callable  # 类型提示

from fastapi import Depends, HTTPException, status  # FastAPI 依赖注入与异常
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # Bearer 认证
from jose import JWTError, jwt  # JWT 编解码
from passlib.context import CryptContext  # 密码哈希

from config.settings import settings  # 引入配置
from app.db.migrate_sched import sched_session_scope  # 调度库 Session
from app.db.models_sched import AuthToken, User  # ORM 模型
from app.utils.logger import get_logger  # 日志工具

LOGGER = get_logger(__name__)  # 初始化日志

PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")  # 配置密码哈希方案
SECURITY_SCHEME = HTTPBearer(auto_error=False)  # 配置 Bearer 认证
ROLE_PRIORITY = {"admin": 3, "operator": 2, "viewer": 1}  # 角色优先级


@dataclass
class UserPrincipal:  # 用户主体数据类
    """封装当前登录用户的信息。"""  # 中文说明

    id: int  # 用户 ID
    username: str  # 用户名
    role: str  # 角色


def hash_password(password: str) -> str:  # 哈希函数
    """对输入密码进行加盐哈希。"""  # 中文说明

    return PWD_CONTEXT.hash(password)  # 返回哈希值


def verify_password(password: str, hashed: str) -> bool:  # 校验函数
    """校验明文密码是否与哈希匹配。"""  # 中文说明

    return PWD_CONTEXT.verify(password, hashed)  # 返回布尔结果


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:  # 创建 JWT
    """生成访问令牌，默认使用配置中的过期时间。"""  # 中文说明

    expire_delta = timedelta(minutes=expires_minutes or settings.jwt_access_expire_min)  # 计算过期时间
    to_encode = {"sub": subject, "role": role, "exp": datetime.utcnow() + expire_delta}  # 构造 payload
    token = jwt.encode(to_encode, settings.dashboard_jwt_secret, algorithm="HS256")  # 生成 JWT
    LOGGER.debug("签发 JWT 用户=%s 角色=%s", subject, role)  # 记录日志
    return token  # 返回 token


def decode_token(token: str) -> dict:  # 解码函数
    """解码并验证 JWT，失败时抛出 HTTPException。"""  # 中文说明

    try:
        payload = jwt.decode(token, settings.dashboard_jwt_secret, algorithms=["HS256"])  # 解码
        return payload  # 返回 payload
    except JWTError as exc:  # 捕获解码错误
        LOGGER.warning("JWT 解码失败 error=%s", exc)  # 记录警告
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")  # 抛出异常


def get_current_user(required_role: str | None = None) -> Callable:  # 构造依赖函数
    """返回 FastAPI 依赖，用于鉴权并检查角色。"""  # 中文说明

    def dependency(credentials: HTTPAuthorizationCredentials = Depends(SECURITY_SCHEME)) -> UserPrincipal:  # 内部函数
        if credentials is None or not credentials.credentials:  # 未提供凭证
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")  # 抛出异常
        payload = decode_token(credentials.credentials)  # 解码 token
        username = payload.get("sub")  # 获取用户名
        role = payload.get("role")  # 获取角色
        if username is None or role is None:  # 校验 payload
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")  # 抛出异常
        with sched_session_scope() as session:  # 查询数据库
            user = session.query(User).filter(User.username == username).one_or_none()  # 查找用户
            if user is None or not user.is_active:  # 校验用户状态
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User disabled")  # 抛出异常
            if required_role and ROLE_PRIORITY.get(user.role, 0) < ROLE_PRIORITY.get(required_role, 0):  # 校验权限
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")  # 抛出异常
            return UserPrincipal(id=user.id, username=user.username, role=user.role)  # 返回主体

    return dependency  # 返回依赖函数


def revoke_token(jti: str, user_id: int, expires_at: datetime) -> None:  # 令牌黑名单函数
    """将 JWT jti 写入数据库，后续可用于注销。"""  # 中文说明

    with sched_session_scope() as session:  # 打开 Session
        record = AuthToken(user_id=user_id, jti=jti, expires_at=expires_at)  # 创建记录
        session.add(record)  # 添加记录
        LOGGER.info("记录已注销的 token user_id=%s jti=%s", user_id, jti)  # 记录日志
