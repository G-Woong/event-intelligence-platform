"""google_trends_explore RATE_LIMITED 재검증 backend 정책(05) — 네트워크/브라우저 없음.

standalone run_playwright_probe는 기본 memory backend라 429 cooldown이 디스크에
영속되지 않는다. 이는 코드 결함이 아니라 의도된 dev 기본값이며, RATE_LIMITED 검증/
주기 수집에서는 local_file backend를 강제해야 한다. 아래 테스트로 정책을 코드로 고정한다.
"""
import os

import pytest

from ingestion.core import rate_limit_policy as rlp
from ingestion.core import rate_limit_store as rls


@pytest.fixture(autouse=True)
def _isolate_backend():
    # 파일 단위 격리: env/singleton을 깨끗이 두고 시작·종료한다(실제 cache 파일 미오염).
    os.environ.pop("INGESTION_RATE_LIMIT_BACKEND", None)
    rls.reset_store_for_tests()
    yield
    os.environ.pop("INGESTION_RATE_LIMIT_BACKEND", None)
    rls.reset_store_for_tests()


def test_local_file_backend_persists_429_cooldown_across_restart(tmp_path, monkeypatch):
    """local_file backend에서 record_rate_limited → 파일 영속 → 재기동 후에도 next_retry 유지."""
    path = tmp_path / "rate_limit_cache.json"
    store = rls.LocalPersistentRateLimitStore(path)
    monkeypatch.setattr(rls, "get_store", lambda: store)

    iso = rlp.record_rate_limited("google_trends_explore", "이재명", cooldown_seconds=3600)
    assert path.exists()  # 디스크에 기록됨

    # 새 프로세스 = 새 인스턴스. 같은 파일을 읽어 cooldown이 살아있어야 한다.
    reopened = rls.LocalPersistentRateLimitStore(path)
    assert reopened.get_next_retry_at("google_trends_explore:이재명") == iso


def test_memory_backend_does_not_persist_cooldown_is_expected(monkeypatch):
    """memory backend는 in-process에만 기록 — 재기동 시 소실(코드 결함 아님, 의도된 동작)."""
    store = rls.InMemoryRateLimitStore({})
    monkeypatch.setattr(rls, "get_store", lambda: store)

    rlp.record_rate_limited("google_trends_explore", "이재명", cooldown_seconds=3600)
    # 같은 인스턴스 내에서는 보임
    assert store.get_next_retry_at("google_trends_explore:이재명") is not None
    # 재기동 아날로그(새 memory 인스턴스)에는 아무것도 없음 → 영속 안 됨(설계상 기대값)
    fresh = rls.InMemoryRateLimitStore({})
    assert fresh.get_next_retry_at("google_trends_explore:이재명") is None


def test_select_backend_forces_local_file():
    """_select_rate_limit_backend('local_file') → get_store()가 LocalPersistent 반환."""
    from ingestion.probes import playwright_probe as pp

    pp._select_rate_limit_backend("local_file")
    assert os.environ["INGESTION_RATE_LIMIT_BACKEND"] == "local_file"
    assert isinstance(rls.get_store(), rls.LocalPersistentRateLimitStore)


def test_select_backend_none_is_noop():
    """backend=None이면 env 미설정 + memory 기본 유지(dev 경로 — 기존 동작 불변)."""
    from ingestion.probes import playwright_probe as pp

    pp._select_rate_limit_backend(None)
    assert "INGESTION_RATE_LIMIT_BACKEND" not in os.environ
    assert isinstance(rls.get_store(), rls.InMemoryRateLimitStore)


def test_cli_main_forces_local_file_before_probe(monkeypatch):
    """main(--rate-limit-backend local_file)이 probe 호출 전에 backend를 강제하는지(브라우저 없이)."""
    from ingestion.probes import playwright_probe as pp
    from ingestion.probes.models import ProbeResult

    seen = {}

    def fake_probe(site_id, query=None, region=None, max_items=10):
        seen["backend_type"] = type(rls.get_store()).__name__
        seen["site"] = site_id
        return ProbeResult(
            source_id=site_id, method="playwright", status="RATE_LIMITED",
            error_category="RATE_LIMITED",
        )

    monkeypatch.setattr(pp, "run_playwright_probe", fake_probe)
    rc = pp.main([
        "--site", "google_trends_explore", "--query", "이재명",
        "--region", "KR", "--rate-limit-backend", "local_file",
    ])
    assert rc == 0
    assert seen["site"] == "google_trends_explore"
    assert seen["backend_type"] == "LocalPersistentRateLimitStore"
