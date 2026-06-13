"""수집 runner/script 오케스트레이션 준비도 audit (docs/10 PHASE 7).

각 수집 스크립트가 에이전트 오케스트레이션에서 호출 가능한지 재감사한다:
  · `--help` 실행 가능 여부 + exit code (subprocess)
  · 출력 JSONL 계약(structured status field) 존재 여부
  · source_id/status·final_status·classification + next_action/next_retry_at 등
    agent가 다음 action을 결정할 수 있는 필드 존재 여부
라이브러리 모듈(CLI 없음)은 programmatic 호출 대상으로 분류한다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    safe_print,
    write_audit_jsonl,
    write_audit_md,
)

_ID_FIELDS = ("source_id", "script", "site_id", "site", "source")
_STATUS_FIELDS = ("status", "final_status", "final_classification", "verdict")
_ACTION_FIELDS = ("next_action", "next_retry_at", "final_status", "audit_action", "candidates")

# (module, jsonl_prefix | None, is_library, note)
_TARGETS: list[tuple[str, Optional[str], bool, str]] = [
    ("ingestion.runners.run_primary_seed_live_audit", "primary_seed_live_audit_", False, "1차 seed live audit"),
    ("ingestion.runners.run_enrichment_live_audit", "enrichment_live_audit_", False, "2차 enrichment live audit"),
    ("ingestion.runners.run_conditional_sources_e2e_audit", "conditional_sources_e2e_audit_", False, "01~05 조건부 E2E"),
    ("ingestion.runners.run_playwright_selector_sources_audit", "playwright_selector_sources_e2e_audit_", False, "playwright selector E2E"),
    ("ingestion.runners.run_api_partial_sources_audit", "api_partial_sources_e2e_audit_", False, "08 API partial E2E"),
    ("ingestion.runners.run_external_rate_limit_recheck", "external_rate_limit_recheck_", False, "외부 rate-limit 재검증"),
    ("ingestion.runners.run_trend_fallback_enrichment_audit", "trend_fallback_enrichment_audit_", False, "Trends fallback enrichment"),
    ("ingestion.runners.run_structure_explorer", "structure_explorer_", False, "DOM selector 채굴"),
    ("ingestion.tools.check_dependency_readiness", None, False, "의존성 readiness (자체 JSON)"),
    ("ingestion.tools.scan_secrets", None, False, "secret scan (--json 리포트)"),
    ("ingestion.tools.feed_discovery", None, True, "RSS/sitemap 발견 라이브러리"),
    ("ingestion.tools.url_resolver", None, True, "canonical URL 해석 라이브러리"),
    ("ingestion.fetch_strategies.article_body_extractor", None, True, "본문 추출 라이브러리"),
]


def _latest_jsonl(prefix: str) -> Optional[Path]:
    files = sorted(OUTPUT_JSONL_DIR.glob(f"{prefix}*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _check_help(module: str) -> tuple[int, bool]:
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=60, cwd=str(_REPO_ROOT), env=env,
        )
        out = (r.stdout or "") + (r.stderr or "")
        has_cli = "usage:" in out or "--help" in out
        return r.returncode, has_cli
    except Exception:
        return 1, False


def _check_contract(prefix: Optional[str]) -> dict:
    if prefix is None:
        return {"output_contract_ok": None, "required_fields_present": None,
                "jsonl_path": None}
    art = _latest_jsonl(prefix)
    if not art:
        return {"output_contract_ok": False, "required_fields_present": False,
                "jsonl_path": None}
    try:
        first = next(l for l in art.read_text(encoding="utf-8").splitlines() if l.strip())
        row = json.loads(first)
    except Exception:
        return {"output_contract_ok": False, "required_fields_present": False,
                "jsonl_path": str(art)}
    keys = set(row.keys())
    has_id = any(k in keys for k in _ID_FIELDS)
    has_status = any(k in keys for k in _STATUS_FIELDS)
    has_action = any(k in keys for k in _ACTION_FIELDS)
    ok = has_id and has_status and has_action
    return {"output_contract_ok": ok,
            "required_fields_present": {"id": has_id, "status": has_status, "action": has_action},
            "jsonl_path": str(art)}


def audit_one(module: str, prefix: Optional[str], is_library: bool, note: str) -> dict:
    code, has_cli = _check_help(module)
    contract = _check_contract(prefix)
    runnable = code == 0
    if is_library:
        agent_ready = runnable  # import 성공이면 programmatic 호출 가능
        failure = None if runnable else "import_failed"
        next_action = "call_programmatically"
    else:
        # CLI 도구: agent가 호출+인자발견(has_cli) 가능하고 구조화 출력을 내면 ready.
        # 파일 JSONL이 없는 도구(scan_secrets/check_dependency)는 stdout JSON으로 계약 충족.
        ok = contract["output_contract_ok"]
        emits_structured = (ok is True) or (prefix is None)  # prefix None = stdout-JSON 도구
        agent_ready = bool(runnable and has_cli and emits_structured)
        failure = None
        if not runnable:
            failure = "help_nonzero_exit"
        elif not has_cli:
            failure = "no_argparse_cli"
        elif ok is False:
            failure = "missing_or_invalid_jsonl_contract"
        if prefix is None and ok is None:
            contract["output_contract_ok"] = "stdout_json"
        next_action = "ready_for_orchestration" if agent_ready else "fix_cli_or_contract"
    return {
        "script": module,
        "command": f"python -m {module}",
        "exit_code": code,
        "runnable": runnable,
        "has_cli": has_cli,
        "is_library": is_library,
        "output_contract_ok": contract["output_contract_ok"],
        "required_fields_present": contract["required_fields_present"],
        "jsonl_contract_path": contract["jsonl_path"],
        "agent_ready": agent_ready,
        "failure_reason": failure,
        "next_action": next_action,
        "note": note,
    }


def _md_report(rows: list[dict], ts: str) -> str:
    lines = [
        "# Runner Orchestration Readiness (docs/10 PHASE 7)",
        "",
        f"- run: {ts} (UTC)",
        f"- scripts: {len(rows)}",
        "",
        "| script | runnable | cli | output_contract_ok | agent_ready | failure_reason | next_action |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        short = r["script"].split(".")[-1]
        lines.append(
            f"| {short} | {'y' if r['runnable'] else 'n'} | {'y' if r['has_cli'] else 'lib' if r['is_library'] else 'n'} "
            f"| {r['output_contract_ok']} | {'y' if r['agent_ready'] else 'n'} "
            f"| {r['failure_reason'] or '-'} | {r['next_action']} |"
        )
    ready = [r for r in rows if r["agent_ready"]]
    lines += [
        "",
        "## Summary",
        f"- agent_ready: {len(ready)} / {len(rows)}",
        f"- libraries(programmatic): {len([r for r in rows if r['is_library']])}",
        f"- not_ready: {[r['script'].split('.')[-1] for r in rows if not r['agent_ready']]}",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Runner orchestration readiness audit")
    args = parser.parse_args(argv)

    rows: list[dict] = []
    for module, prefix, is_lib, note in _TARGETS:
        safe_print(f"[readiness] {module} ...")
        r = audit_one(module, prefix, is_lib, note)
        rows.append(r)
        safe_print(f"    -> agent_ready={r['agent_ready']} contract={r['output_contract_ok']} "
                   f"failure={r['failure_reason']}")

    ts = audit_timestamp()
    jsonl = write_audit_jsonl(rows, OUTPUT_JSONL_DIR / f"runner_orchestration_readiness_{ts}.jsonl")
    md = write_audit_md(_md_report(rows, ts), OUTPUT_REPORTS_DIR / f"runner_orchestration_readiness_{ts}.md")
    safe_print(f"jsonl : {jsonl}")
    safe_print(f"report: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
