"""启动脚本"""

import os

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        # 热重载仅用于本地开发：在 .env 中设 RELOAD=true 开启。
        # 生产环境必须关闭，否则部署上传文件时服务会反复重启，
        # 且传到一半的语法错误文件可能直接把服务搞挂。
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
