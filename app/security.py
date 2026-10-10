"""标准库 PBKDF2-SHA256 密码哈希与签名会话令牌。"""
import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .db import read_connection, transaction


bearer = HTTPBearer(auto_error=False)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("密码至少需要 10 个字符")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(iterations)
        if not 100_000 <= rounds <= 1_000_000:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt), rounds)
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError, binascii.Error):
        return False


def create_token(user_id: int, role: str, duration_seconds: int = 8 * 3600) -> str:
    if len(settings.app_secret) < 32:
        raise RuntimeError("APP_SECRET must be at least 32 characters")
    session_id = _b64(secrets.token_bytes(32))
    expires_at = datetime.now() + timedelta(seconds=duration_seconds)
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO auth_session (session_id,user_id,expires_at) VALUES (%s,%s,%s)",
            (session_id, user_id, expires_at),
        )
    payload = {"uid": user_id, "role": role, "sid": session_id, "exp": int(time.time()) + duration_seconds}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(settings.app_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        body, provided_signature = credentials.credentials.split(".", 1)
        expected = hmac.new(settings.app_secret.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(provided_signature)):
            raise unauthorized
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            raise unauthorized
        user_id = int(payload["uid"])
        session_id = payload["sid"]
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
        raise unauthorized from None
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT u.user_id,u.username,u.role,u.is_active,u.must_change_password "
            "FROM user_account u JOIN auth_session s ON s.user_id=u.user_id "
            "WHERE u.user_id=%s AND s.session_id=%s AND s.revoked_at IS NULL "
            "AND s.expires_at>NOW()",
            (user_id, session_id),
        )
        user = cursor.fetchone()
    if not user or not user["is_active"] or user["role"] != payload.get("role"):
        raise unauthorized
    user["session_id"] = session_id
    return user


def revoke_session(session_id: str, user_id: int) -> None:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE auth_session SET revoked_at=NOW() WHERE session_id=%s AND user_id=%s AND revoked_at IS NULL",
            (session_id, user_id),
        )


def require_role(*roles: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["must_change_password"]:
            raise HTTPException(status_code=403, detail="请先修改初始密码")
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="没有执行此操作的权限")
        return user

    return dependency
