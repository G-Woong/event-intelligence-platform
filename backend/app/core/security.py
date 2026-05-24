from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from backend.app.core.config import settings


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = settings.ADMIN_API_TOKEN
    if not expected:
        return
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="invalid admin token")
