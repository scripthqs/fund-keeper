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
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-pro")
    # 快速模型（非推理模型，用于策略推荐/宏观分析/情绪文案等规则明确的场景，速度快 2-3 倍）
    # 留空则全部场景使用 LLM_MODEL
    LLM_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "")

    # 通用密码（可登录任意账号，为空则不启用）
    UNIVERSAL_PASSWORD: str = os.getenv("UNIVERSAL_PASSWORD", "")

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
    def fast_model(self) -> str:
        """快速模型：配置了 LLM_FAST_MODEL 则用之，否则回退到 LLM_MODEL"""
        return self.LLM_FAST_MODEL or self.LLM_MODEL


settings = Settings()
