"""管理员路由 - 账号管理（仅 admin 可访问）"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db, gen_id, now_str

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ==================== 校验 admin 身份的依赖 ====================

def verify_admin(x_username: str = Header(None, alias="X-Username")) -> str:
    """验证是否为 admin 用户，返回用户名"""
    if not x_username or x_username.strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    return x_username.strip()


# ==================== 请求/响应模型 ====================

class AccountInfo(BaseModel):
    id: str
    username: str
    password: str
    created_at: str = ""


class AccountListResponse(BaseModel):
    accounts: List[AccountInfo]


class AddAccountRequest(BaseModel):
    username: str
    password: str


# ==================== API ====================

@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(admin: str = Header(None, alias="X-Username")):
    """查看所有账号及其密码"""
    verify_admin(admin)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, username, password, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        accounts = [
            AccountInfo(
                id=row["id"],
                username=row["username"],
                password=row["password"],
                created_at=row["created_at"] or "",
            )
            for row in rows
        ]
        return AccountListResponse(accounts=accounts)
    finally:
        conn.close()


@router.delete("/accounts/{user_id}")
def delete_account(
    user_id: str,
    admin: str = Header(None, alias="X-Username"),
):
    """删除指定账号（不能删除 admin 自己）"""
    verify_admin(admin)
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="账号不存在")
        if user["username"].lower() == "admin":
            raise HTTPException(status_code=400, detail="不能删除 admin 账号")

        # 删除用户及其关联数据
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM funds WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM config WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM snapshots WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"ok": True, "message": f"已删除账号 {user['username']} 及其所有数据"}
    finally:
        conn.close()


@router.post("/accounts")
def add_account(
    req: AddAccountRequest,
    admin: str = Header(None, alias="X-Username"),
):
    """添加新账号"""
    verify_admin(admin)
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

        user_id = gen_id()
        created_at = now_str()
        conn.execute(
            "INSERT INTO users (id, username, password, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, password, created_at),
        )
        conn.commit()
        return {
            "ok": True,
            "message": f"账号 {username} 创建成功",
            "account": {
                "id": user_id,
                "username": username,
                "password": password,
                "created_at": created_at,
            },
        }
    finally:
        conn.close()
