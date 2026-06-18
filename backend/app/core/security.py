from __future__ import annotations

import logging
import secrets

from fastapi import Header, HTTPException

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# 운영성 환경: admin 토큰 미설정을 dev 편의 bypass로 허용하지 않는다(fail-closed).
_PROD_LIKE_ENVS = frozenset({"production", "staging"})


def _is_prod_like() -> bool:
    return settings.APP_ENV in _PROD_LIKE_ENVS


def assert_startup_auth_posture() -> None:
    """기동 시 admin 인증 자세를 강제/경고한다(main.py lifespan에서 단일 호출).

    prod-like 판정을 require_admin_token 과 같은 출처(`_is_prod_like`)로 공유해 드리프트를 막는다.
      - production/staging + 토큰 미설정 → RuntimeError(기동 거부, fail-closed).
      - dev/test + 토큰 미설정 → 무인증 + 운영 오배포 방지 경고(APP_ENV=dev로 공개 배포하는 실수 차단).
    """
    if settings.ADMIN_API_TOKEN:
        return
    if _is_prod_like():
        raise RuntimeError(
            f"ADMIN_API_TOKEN required when APP_ENV={settings.APP_ENV} (refusing to start unauthenticated)"
        )
    logger.warning(
        "ADMIN_API_TOKEN unset and APP_ENV=%s — admin/internal endpoints are UNAUTHENTICATED. "
        "This is for local dev only. Before ANY non-local/public deployment set "
        "APP_ENV=production AND a strong ADMIN_API_TOKEN.",
        settings.APP_ENV,
    )


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
