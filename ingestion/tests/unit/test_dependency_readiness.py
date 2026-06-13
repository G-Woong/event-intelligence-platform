"""check_dependency_readiness(09 §1) 단위 테스트 — 네트워크/브라우저 launch 없음.

import 점검 함수는 가짜 모듈명에 MISSING을, 실제 모듈에 READY를 반환해야 한다.
chromium launch 점검은 실제 브라우저를 띄우므로 단위 테스트에서 호출하지 않는다
(통합 실행은 `python -m ingestion.tools.check_dependency_readiness`로 별도 검증).
"""
from ingestion.tools import check_dependency_readiness as cdr


def test_check_imports_flags_fake_module_missing():
    rows = cdr.check_imports(["definitely_not_a_real_module_xyz"])
    assert len(rows) == 1
    assert rows[0]["status"] == "MISSING"
    assert rows[0]["component"] == "import:definitely_not_a_real_module_xyz"
    assert rows[0]["fix"]  # 설치 안내 문구 존재


def test_check_imports_real_module_ready():
    rows = cdr.check_imports(["json", "httpx"])
    assert all(r["status"] == "READY" for r in rows)
    assert {r["component"] for r in rows} == {"import:json", "import:httpx"}


def test_required_modules_list_covers_core_runtime():
    # 09 §1이 요구하는 핵심 런타임 의존성이 점검 목록에 누락되지 않았는지 고정
    required = set(cdr._REQUIRED_MODULES)
    for name in ("playwright", "selenium", "trafilatura", "readability",
                 "bs4", "lxml", "feedparser", "httpx", "langgraph"):
        assert name in required, f"{name}이 의존성 점검 목록에서 누락됐다"


def test_check_state_writable(tmp_path):
    # tmp repo root에 outputs/state를 만들고 write→delete 권한 확인
    out = cdr.check_state_writable(repo_root=tmp_path)
    assert out["status"] == "READY"
    assert out["component"] == "state_writable"
    # 점검 후 tmp probe 파일이 남지 않아야 한다
    probe = tmp_path / "ingestion" / "outputs" / "state" / ".readiness_write_probe.tmp"
    assert not probe.exists()


def test_check_rate_limit_backend_is_informational(tmp_path):
    out = cdr.check_rate_limit_backend(repo_root=tmp_path)
    assert out["status"] == "READY"  # 정보성 — 항상 READY
    assert "backend=" in out["fix"]
