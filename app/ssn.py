"""演示用 SSN 输入校验与加密；API 永不返回号码或密文。"""
from __future__ import annotations

import base64
import hashlib
import re

from cryptography.fernet import Fernet
from fastapi import HTTPException

from .config import settings


def encrypt_ssn(value: str | None) -> bytes | None:
    if value is None or not value.strip():
        return None
    raw = value.strip()
    if not re.fullmatch(r"(?:[0-9]{9}|[0-9]{3}-[0-9]{2}-[0-9]{4})", raw):
        raise HTTPException(400, "SSN 须为 9 位数字，可写成 123-45-6789；演示只使用虚构号码")
    compact = raw.replace("-", "")
    if len(settings.app_secret) < 32:
        raise RuntimeError("APP_SECRET must be at least 32 characters before storing SSN")
    # 与登录令牌采用不同用途的派生密钥；更换 APP_SECRET 后旧号码无法解密。
    digest = hashlib.sha256(b"course-registration:ssn:v1:" + settings.app_secret.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key).encrypt(compact.encode("ascii"))
