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


class _Result:
    __slots__ = ("data",)
    def __init__(self, data): self.data = data


class _Query:
    """Minimal fluent PostgREST query builder (HTTP/1.1 only, no supabase-py)."""

    def __init__(self, base_url: str, headers: dict, table: str):
        self._url     = f"{base_url}/{table}"
        self._headers = headers
        self._params: dict = {}
        self._method  = "select"
        self._payload = None

    def select(self, cols: str = "*") -> "_Query":
        self._params["select"] = cols
        return self

    def eq(self, col: str, val) -> "_Query":
        self._params[col] = f"eq.{val}"
        return self

    def order(self, col: str) -> "_Query":
        self._params["order"] = col
        return self

    def insert(self, data: dict) -> "_Query":
        self._method  = "insert"
        self._payload = data
        return self

    def delete(self) -> "_Query":
        self._method = "delete"
        return self

    def execute(self) -> _Result:
        import httpx
        with httpx.Client(http2=False, timeout=10.0) as client:
            if self._method == "select":
                r = client.get(self._url, headers=self._headers, params=self._params)
            elif self._method == "insert":
                r = client.post(self._url, headers=self._headers, json=self._payload)
            elif self._method == "delete":
                r = client.delete(self._url, headers=self._headers, params=self._params)
            else:
                raise ValueError(f"Méthode inconnue : {self._method}")

        if not r.is_success:
            try:
                msg = r.json().get("message", r.text)
            except Exception:
                msg = r.text
            raise Exception(f"PostgREST {r.status_code}: {msg}")

        data = r.json() if r.content else []
        return _Result(data if isinstance(data, list) else [data])


class _SupabaseClient:
    def __init__(self, url: str, key: str):
        self._base    = f"{url}/rest/v1"
        self._headers = {
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=representation",
        }

    def table(self, name: str) -> _Query:
        return _Query(self._base, self._headers, name)


def supabase_client() -> _SupabaseClient:
    """PostgREST client over HTTP/1.1 — contourne les problèmes HTTP/2 serverless."""
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise HTTPException(
            503,
            "Supabase non configuré — ajoutez SUPABASE_URL et SUPABASE_SERVICE_KEY "
            "dans vos variables d'environnement",
        )
    return _SupabaseClient(url, key)
