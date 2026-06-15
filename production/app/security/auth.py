"""OAuth2 password flow with JWT bearer tokens and RBAC.

Roles (least -> most privileged): constable, investigator, analyst, admin.
Password hashing uses bcrypt (passlib); tokens are signed with HS256 (python-jose).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import User

ROLES = ("constable", "investigator", "analyst", "admin")
# Privilege ordering for hierarchical checks (admin implies everything below).
_ROLE_RANK = {r: i for i, r in enumerate(ROLES)}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(plain: str) -> str:
    # bcrypt caps input at 72 bytes; truncate defensively.
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str, role: str, expires_min: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_min or settings.JWT_EXPIRE_MIN
    )
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        username: str | None = payload.get("sub")
        if not username:
            raise cred_exc
    except JWTError:
        raise cred_exc
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise cred_exc
    return user


def require_role(*roles: str):
    """Dependency factory. Allows the listed roles OR any higher-ranked role.

    e.g. ``require_role("investigator")`` admits investigator/analyst/admin.
    """
    allowed = set(roles)
    min_rank = min((_ROLE_RANK.get(r, 0) for r in roles), default=0)

    def _checker(user: User = Depends(get_current_user)) -> User:
        rank = _ROLE_RANK.get(user.role, -1)
        if user.role in allowed or rank >= min_rank:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires one of roles: {sorted(allowed)}",
        )

    return _checker
