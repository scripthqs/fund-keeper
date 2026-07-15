"""FastAPI 主应用 - 注册路由、CORS、静态文件服务"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings, FRONTEND_DIR
from app.database import init_db
from app.routers import funds, config, history, chat, snapshots

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 初始化数据库
init_db()
logger.info("数据库初始化完成")

app = FastAPI(
    title="理财小助理 API",
    description="基于 HelloAgents 的基金投资决策辅助工具后端",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(funds.router)
app.include_router(config.router)
app.include_router(history.router)
app.include_router(chat.router)
app.include_router(snapshots.router)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "model": settings.LLM_MODEL,
    }


# ==================== 前端静态文件服务 ====================

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        """返回前端首页"""
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """
        前端路由兜底：非 /api 路径的请求都返回前端文件
        部署时只需运行后端，前端由后端一并托管
        """
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    logger.warning(
        "前端目录不存在: %s（仅 API 模式，请将前端文件放入 frontend/ 目录）",
        FRONTEND_DIR,
    )
