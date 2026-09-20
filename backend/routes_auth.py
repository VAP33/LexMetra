from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

import auth
from db import persistence as db

router = APIRouter(tags=["auth"])

# Authentication endpoints
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = None
    role: str = "inspector"


@router.post("/auth/register")
def register(req: RegisterRequest):
    """
    Create a user account.

    Bootstrap rule: if no user exists yet in the database, the very first
    registration is allowed without authentication and is granted 'admin' so
    the system is operable on first deployment. Every subsequent registration
    requires an authenticated admin caller.
    """
    if req.role not in auth.ROLE_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    if db.any_user_exists():
        raise HTTPException(
            status_code=401,
            detail=(
                "An account already exists. Use an authenticated admin "
                "session to create additional users (see /auth/login, then "
                "call this endpoint with a Bearer token)."
            ),
        )

    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already exists.")

    role = req.role if db.any_user_exists() else "admin"
    record = db.create_user(
        username=req.username,
        hashed_password=auth.hash_password(req.password),
        role=role,
        full_name=req.full_name,
    )
    db.record_audit_event(
        action="user_created", actor_username=req.username,
        resource_type="user", resource_id=req.username,
        detail=f"role={role} (bootstrap)",
    )
    return {"user_id": record["user_id"], "username": record["username"], "role": record["role"]}


@router.post("/auth/register/admin")
def register_by_admin(
    req: RegisterRequest,
    current_user: auth.CurrentUser = Depends(auth.require_admin),
):
    """Admin-only endpoint to create additional accounts of any role."""
    if req.role not in auth.ROLE_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")
    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already exists.")

    record = db.create_user(
        username=req.username,
        hashed_password=auth.hash_password(req.password),
        role=req.role,
        full_name=req.full_name,
    )
    db.record_audit_event(
        action="user_created", actor_username=current_user.username,
        resource_type="user", resource_id=req.username, detail=f"role={req.role}",
    )
    return {"user_id": record["user_id"], "username": record["username"], "role": record["role"]}


@router.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        db.record_audit_event(action="login_failed", actor_username=form_data.username)
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.create_access_token(user.username, user.role)
    db.record_audit_event(action="login_success", actor_username=user.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


@router.get("/auth/me")
def read_current_user(current_user: auth.CurrentUser = Depends(auth.get_current_user)):
    return current_user


@router.get("/audit-log")
def get_audit_log(
    limit: int = 100,
    current_user: auth.CurrentUser = Depends(auth.require_admin),
):
    return db.list_audit_log(limit=limit)


