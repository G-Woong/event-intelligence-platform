from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from backend.app.core.config import settings

# 운영성 환경: admin 토큰 미설정을 dev 편의 bypass로 허용하지 않는다(fail-closed).
_PROD_LIKE_ENVS = frozenset({"production", "staging"})


def _is_prod_like() -> bool:
    return settings.APP_ENV in _PROD_LIKE_ENVS


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = settings.ADMIN_API_TOKEN
    if not expected:
        # 운영(production/staging)에서는 토큰 미설정을 거부한다. dev/test만 bypass 허용.
        if _is_prod_like():
            raise HTTPException(
                status_code=503,
                detail="admin auth not configured (ADMIN_API_TOKEN required in this environment)",
            )
        return
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="invalid admin token")
