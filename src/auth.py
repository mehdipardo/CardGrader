"""Authentication utilities: password hashing and JWT tokens."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Header, HTTPException
from passlib.context import CryptContext

_pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGO     = "HS256"
_EXP_DAYS = 30


def _jwt_secret() -> str:
    s = os.environ.get("JWT_SECRET")
    if not s:
        raise HTTPException(503, "JWT_SECRET non configuré")
    return s


def hash_password(pw: str) -> str:
    return _pwd_ctx.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return _pwd_ctx.verify(pw, hashed)


def create_token(user_id: str, pseudo: str) -> str:
    payload = {
        "sub":    user_id,
        "pseudo": pseudo,
        "exp":    datetime.now(timezone.utc) + timedelta(days=_EXP_DAYS),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_ALGO)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expirée, reconnectez-vous")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token invalide")


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency: extracts and validates Bearer JWT, returns payload."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Non authentifié")
    return _decode_token(authorization[7:])


def supabase_client():
    """Return a Supabase client using the service-role key (bypasses RLS)."""
    try:
        from supabase import create_client
    except ImportError:
        raise HTTPException(503, "Module supabase non installé (pip install supabase)")
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise HTTPException(
            503,
            "Supabase non configuré — ajoutez SUPABASE_URL et SUPABASE_SERVICE_KEY "
            "dans vos variables d'environnement",
        )
    return create_client(url, key)
