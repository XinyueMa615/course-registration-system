"""应用配置。

优先读取项目根目录的 .env，再读取系统环境变量。配置集中在这里，避免在
业务代码和一次性脚本中重复保存数据库账号与密码。
"""

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = os.getenv("DB_HOST", "127.0.0.1")
    port: int = int(os.getenv("DB_PORT", "3306"))
    user: str = os.getenv("DB_USER", "school_app")
    password: str = os.getenv("DB_PASSWORD", "")
    database: str = os.getenv("DB_NAME", "school_db")


DATABASE = DatabaseSettings()
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]

