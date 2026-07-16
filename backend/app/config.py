"""应用配置 - 从环境变量 / .env 文件读取"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 项目路径
BASE_DIR = Path(__file__).resolve().parent.parent

# 前端目录查找顺序：
# 1. 服务器部署模式：BASE_DIR/../dist（dist 和 backend 同级）
# 2. 本地开发构建：BASE_DIR/../frontend/dist
# 3. 本地开发源码：BASE_DIR/../frontend（开发模式下 Vite dev server 运行，此目录仅用于判断存在性）
_SERVER_DIST = BASE_DIR.parent / "dist"
_LOCAL_DIST = BASE_DIR.parent / "frontend" / "dist"
_LOCAL_SRC = BASE_DIR.parent / "frontend"

if _SERVER_DIST.exists():
    FRONTEND_DIR = _SERVER_DIST          # 服务器部署模式
elif _LOCAL_DIST.exists():
    FRONTEND_DIR = _LOCAL_DIST           # 本地 build 后
else:
    FRONTEND_DIR = _LOCAL_SRC            # 开发模式（前端由 Vite dev server 运行）

# 数据库路径
DB_PATH = BASE_DIR / "data" / "fund_keeper.db"


class Settings:
    """应用配置单例"""

    # LLM 配置（支持 DeepSeek / OpenAI 等兼容接口）
    # DeepSeek V4 系列（v4-pro / v4-flash）原生支持多模态识图
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    LLM_VISION_MODEL: str = os.getenv("LLM_VISION_MODEL", "deepseek-v4-pro")  # 多模态识图，V4-Pro 原生支持

    # 服务配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # CORS（生产环境建议改为你的域名）
    CORS_ORIGINS: list = os.getenv(
        "CORS_ORIGINS", "*"
    ).split(",")

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY)

    @property
    def vision_model(self) -> str:
        """返回实际用于识图的模型名（支持单独配置或回退到主模型）"""
        return self.LLM_VISION_MODEL if self.LLM_VISION_MODEL else self.LLM_MODEL


settings = Settings()
