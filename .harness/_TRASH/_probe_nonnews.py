"""throwaway — keyless 비뉴스 소스 실 fetch(시스템 probe 머신 경유, rate-gate 준수). 커밋 금지."""
from pathlib import Path

from ingestion.probes.api_probe import run_api_live_probe

ENV = Path("C:/Users/computer/Desktop/business/claude/.env")

for sid in ("federal_register", "hacker_news", "sec_edgar"):
    try:
        r = run_api_live_probe(sid, max_calls=1, env_path=ENV if ENV.exists() else None)
        print(f"{sid}: status={r.status} http={r.http_status} items_found={r.items_found} "
              f"err={getattr(r, 'error_category', None)} next={getattr(r, 'next_action', None)}")
    except Exception as e:
        print(f"{sid}: EXC {type(e).__name__}: {e}")
