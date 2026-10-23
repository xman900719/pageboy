"""单 owner 私网鉴权，供现有 API 与导入流程组合复用。"""
import hmac
import os
from fastapi import Header, HTTPException


def require_owner(authorization: str | None = Header(default=None)) -> str:
    expected = os.getenv("SHUTONG_TOKEN")
    if not expected:
        raise HTTPException(503, detail="SHUTONG_TOKEN is not configured")
    if authorization is None or not authorization.startswith("Bearer ") or not hmac.compare_digest(authorization[7:], expected):
        raise HTTPException(401, detail="Owner authorization required", headers={"WWW-Authenticate": "Bearer"})
    return "owner"
