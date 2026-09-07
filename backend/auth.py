"""
Authentication and role-based access control (RBAC).

Design goals:
- Passwords are never stored or logged in plaintext (bcrypt via passlib).
- JWTs carry only username + role; the database remains the source of truth
  for account status (is_active).
- This module never makes a legal compliance decision. It only answers
  "who is this" and "are they allowed to call this endpoint".

Roles (least to most privileged):
    inspector -> create inspections, view own/all inspections, view history
    reviewer  -> inspector permissions + resolve UNCERTAIN findings, mark reviewed
    admin     -> reviewer permissions + manage user accounts
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

import config
from db import persistence as db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ROLE_HIERARCHY = {"inspector": 0, "reviewer": 1, "admin": 2}


class TokenData(BaseModel):
    username: str
    role: str


class CurrentUser(BaseModel):
    user_id: int
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool = True


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=config.JWT_EXPIRE_MINUTES
    )
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM]
        )
        username = payload.get("sub")
        role = payload.get("role")
        if not username or not role:
            raise credentials_exception
        return TokenData(username=username, role=role)
    except JWTError as exc:
        raise credentials_exception from exc


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def authenticate_user(username: str, password: str) -> Optional[CurrentUser]:
    record = db.get_user_by_username(username)
    if not record:
        return None
    if not verify_password(password, record["hashed_password"]):
        return None
    if not record.get("is_active", True):
        return None
    return CurrentUser(
        user_id=record["user_id"],
        username=record["username"],
        full_name=record.get("full_name"),
        role=record["role"],
        is_active=record.get("is_active", True),
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> CurrentUser:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    data = decode_access_token(token)
    record = db.get_user_by_username(data.username)
    if not record or not record.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    return CurrentUser(
        user_id=record["user_id"],
        username=record["username"],
        full_name=record.get("full_name"),
        role=record["role"],
        is_active=record.get("is_active", True),
    )


def require_role(minimum_role: str):
    """
    Return a FastAPI dependency that requires at least `minimum_role`
    privilege, using ROLE_HIERARCHY for ordering.
    """

    minimum_level = ROLE_HIERARCHY.get(minimum_role, 0)

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_level = ROLE_HIERARCHY.get(user.role, 0)
        if user_level < minimum_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action requires role '{minimum_role}' or higher; "
                    f"current role is '{user.role}'."
                ),
            )
        return user

    return _check


require_inspector = require_role("inspector")
require_reviewer = require_role("reviewer")
require_admin = require_role("admin")
