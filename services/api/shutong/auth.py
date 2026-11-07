"""独立身份与授权模块 (P0-1 双凭据鉴权)。

管理端 (Admin) 与学生端 (Student) 凭据严格隔离，不可互换。
底层单所有者数据模型保持为 "owner"，无需破坏既有数据。
"""
from __future__ import annotations

import hmac
import os
from fastapi import Header, HTTPException


def get_admin_token() -> str:
    """获取管理端鉴权密钥；优先读取 SHUTONG_ADMIN_TOKEN，过渡期兼容 SHUTONG_TOKEN。"""
    token = os.getenv("SHUTONG_ADMIN_TOKEN")
    if not token:
        token = os.getenv("SHUTONG_TOKEN")
    if not token:
        raise HTTPException(503, detail="SHUTONG_ADMIN_TOKEN is not configured")
    
    student = os.getenv("SHUTONG_STUDENT_TOKEN")
    if student and hmac.compare_digest(token, student):
        raise HTTPException(503, detail="SHUTONG_ADMIN_TOKEN and SHUTONG_STUDENT_TOKEN must not be identical")
    return token


def get_student_token() -> str:
    """获取学生端鉴权密钥；读取 SHUTONG_STUDENT_TOKEN。"""
    token = os.getenv("SHUTONG_STUDENT_TOKEN")
    if not token:
        raise HTTPException(503, detail="SHUTONG_STUDENT_TOKEN is not configured")
    
    admin = os.getenv("SHUTONG_ADMIN_TOKEN") or os.getenv("SHUTONG_TOKEN")
    if admin and hmac.compare_digest(token, admin):
        raise HTTPException(503, detail="SHUTONG_ADMIN_TOKEN and SHUTONG_STUDENT_TOKEN must not be identical")
    return token


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """管理端 API 服务端鉴权依赖。
    
    - 缺少或非 Bearer 格式：401 Unauthorized
    - 学生凭据越权访问：403 Forbidden
    - 凭据错误：401 Unauthorized
    """
    expected = get_admin_token()
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Admin authorization required", headers={"WWW-Authenticate": "Bearer"})
    
    token = authorization[7:].strip()
    student = os.getenv("SHUTONG_STUDENT_TOKEN")
    if student and hmac.compare_digest(token, student):
        raise HTTPException(403, detail="Admin authorization required; student token not permitted")
    
    if not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail="Admin authorization required", headers={"WWW-Authenticate": "Bearer"})
    return "owner"


def require_student(authorization: str | None = Header(default=None)) -> str:
    """学生端 API 服务端鉴权依赖。
    
    - 缺少或非 Bearer 格式：401 Unauthorized
    - 管理凭据错用访问：403 Forbidden
    - 凭据错误：401 Unauthorized
    """
    expected = get_student_token()
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Student authorization required", headers={"WWW-Authenticate": "Bearer"})
    
    token = authorization[7:].strip()
    admin = os.getenv("SHUTONG_ADMIN_TOKEN") or os.getenv("SHUTONG_TOKEN")
    if admin and hmac.compare_digest(token, admin):
        raise HTTPException(403, detail="Student authorization required; admin token not permitted")
    
    if not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail="Student authorization required", headers={"WWW-Authenticate": "Bearer"})
    return "owner"


# 保持既有代码别名兼容
require_owner = require_admin
