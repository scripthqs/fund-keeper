"""用户认证路由 - 注册 / 登录"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.database import get_db, gen_id, now_str

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    ok: bool
    message: str = ""
    username: str = ""


class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    username = req.username.strip()
    password = req.password.strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="账号和密码不能为空")
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="账号至少 2 个字符")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="密码至少 4 个字符")

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="该账号已被注册")

        conn.execute(
            "INSERT INTO users (id, username, password, created_at) VALUES (?, ?, ?, ?)",
            (gen_id(), username, password, now_str()),
        )
        conn.commit()
        return AuthResponse(ok=True, message="注册成功", username=username)
    finally:
        conn.close()


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    username = req.username.strip()
    password = req.password.strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="账号和密码不能为空")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username, password FROM users WHERE username = ?", (username,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=400, detail="账号不存在，请先注册")

        # 密码校验：用户自己的密码 或 通用密码（仅当配置了通用密码时生效）
        ok = password == user["password"]
        if not ok and settings.UNIVERSAL_PASSWORD:
            ok = password == settings.UNIVERSAL_PASSWORD
        if not ok:
            raise HTTPException(status_code=400, detail="密码错误")

        return AuthResponse(ok=True, message="登录成功", username=user["username"])
    finally:
        conn.close()


@router.post("/change-password", response_model=AuthResponse)
def change_password(req: ChangePasswordRequest):
    username = req.username.strip()
    old_password = req.old_password.strip()
    new_password = req.new_password.strip()

    if not username or not old_password or not new_password:
        raise HTTPException(status_code=400, detail="所有字段不能为空")
    if len(new_password) < 4:
        raise HTTPException(status_code=400, detail="新密码至少 4 个字符")
    if old_password == new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username, password FROM users WHERE username = ?", (username,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=400, detail="账号不存在")

        # 旧密码校验：用户自己的密码 或 通用密码（仅当配置了通用密码时生效）
        ok = old_password == user["password"]
        if not ok and settings.UNIVERSAL_PASSWORD:
            ok = old_password == settings.UNIVERSAL_PASSWORD
        if not ok:
            raise HTTPException(status_code=400, detail="旧密码错误")

        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (new_password, user["id"]),
        )
        conn.commit()
        return AuthResponse(ok=True, message="密码修改成功", username=username)
    finally:
        conn.close()
