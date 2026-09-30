"""本地开发启动入口。"""

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "scripts.main:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("APP_RELOAD", "true").lower() == "true",
    )

