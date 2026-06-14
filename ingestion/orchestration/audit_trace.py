"""소스별 오케스트레이션 호출 추적 (Phase E-1, 설계 07/08).

각 소스 audit이 어떤 stage를 거쳤는지 ``AuditTraceEvent``로 남긴다. 실패해도 trace는
남아야 하고(예외가 run을 죽이지 않음), secret/키 값은 절대 metrics/message에 들어가면 안 된다.
저장은 JSONL(기계 판독) + 선택적 console. 시각은 호출자가 주입한다(결정성/테스트 안정성).

stdlib만 사용(json/dataclasses). 신규 설치 0.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# trace에 새어나오면 안 되는 키(부분 일치). 값 노출 방지 마지막 방어선.
_SECRET_MARKERS = (
    "api_key", "apikey", "api-key", "secret", "token", "authorization",
    "password", "passwd", "access_key", "client_secret", "bearer",
)

# 표준 stage 라벨(자유 문자열 허용하되 권장값 명시).
STAGES = (
    "profile_loaded", "strategy_decided", "api_readiness_checked",
    "probe_started", "probe_finished", "seed_created", "artifact_checked",
    "candidate_expansion_started", "candidate_expansion_finished",
    "body_state_assessed", "canonicalized", "quality_pre_gate_applied",
    "sample_saved", "source_completed", "source_failed",
)


def _redact(value: Any) -> Any:
    """metrics 안의 의심 키를 마스킹한다(존재/길이만 남김). 값은 절대 보존하지 않는다."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if any(m in str(k).lower() for m in _SECRET_MARKERS):
                out[k] = "<redacted>"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


@dataclass(frozen=True)
class AuditTraceEvent:
    run_id: str
    source_id: str
    stage: str
    status: str  # ok | warn | error | skip
    timestamp: str
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)
    error_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["metrics"] = _redact(d.get("metrics") or {})
        return d


class TraceRecorder:
    """trace event를 모으고 JSONL로 기록한다. console는 옵션. 실패해도 던지지 않는다."""

    def __init__(self, run_id: str, *, jsonl_path: Optional[str | Path] = None,
                 console: bool = False) -> None:
        self.run_id = run_id
        self.jsonl_path = Path(jsonl_path) if jsonl_path else None
        self.console = console
        self.events: list[AuditTraceEvent] = []
        if self.jsonl_path is not None:
            try:
                self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # 로깅 경로 생성 실패가 audit을 막지 않는다

    def record(self, source_id: str, stage: str, status: str, *,
               timestamp: str, message: str = "",
               metrics: Optional[dict[str, Any]] = None,
               error_type: Optional[str] = None) -> AuditTraceEvent:
        ev = AuditTraceEvent(
            run_id=self.run_id, source_id=source_id, stage=stage, status=status,
            timestamp=timestamp, message=message, metrics=dict(metrics or {}),
            error_type=error_type,
        )
        self.events.append(ev)
        line = json.dumps(ev.to_dict(), ensure_ascii=False)
        if self.jsonl_path is not None:
            try:
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass  # 로깅 실패가 audit을 죽이지 않는다
        if self.console:
            print(line)
        return ev

    def events_for(self, source_id: str) -> list[AuditTraceEvent]:
        return [e for e in self.events if e.source_id == source_id]

    def stage_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.events:
            counts[e.stage] = counts.get(e.stage, 0) + 1
        return counts
