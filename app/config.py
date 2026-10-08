"""本地配置；密码只从环境变量或 Git 忽略的 .env 读取。"""
from dataclasses import dataclass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_local_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "course_reg_app")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_name: str = os.getenv("DB_NAME", "course_registration_v2")
    catalog_db: str = os.getenv("CATALOG_DB", "course_catalog_demo")
    app_secret: str = os.getenv("APP_SECRET", "")
    initial_account_password: str = os.getenv("INITIAL_ACCOUNT_PASSWORD", "")


settings = Settings()
if not settings.catalog_db.replace("_", "").isalnum():
    raise ValueError("CATALOG_DB must contain only letters, digits, and underscores")
