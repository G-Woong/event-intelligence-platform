---
name: artifact-manifest-skill
description: Track ingestion outputs as evidence in artifact_manifest_final.md without committing the raw outputs. Record path, sha256, size, timestamp, runner, and regeneration command. Never copy full article text or secrets.
when_to_use: After new JSONL/report/body/rendered_dom/screenshot artifacts are generated, or before session end when outputs/** changed. Invoke to keep the manifest in sync with ingestion/outputs.
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit
---

# artifact-manifest-skill

`ingestion/outputs/**`는 git에 커밋하지 않는다(.gitignore). 대신 manifest로 증거를 추적한다.

## when_to_use
- 신규 JSONL/report/body/rendered_dom/screenshot 생성 후
- 세션 종료 전 outputs 변경이 있었던 경우

## procedure
1. **신규 artifact 탐색**: `ingestion/outputs/jsonl/`, `reports/`, `body/`, `rendered_dom/`, `screenshots/` 등 최신 파일 (Glob)
2. **manifest 비교**: `docs/ingestion/artifact_manifest_final.md` §2 표와 대조하여 누락 항목 식별
3. **기록 항목** (행당):
   - artifact_path (상대 경로)
   - sha256 앞 16자
   - size (bytes)
   - timestamp
   - 생성 runner / 재생성 command
   - 연관 checklist 항목
4. **Edit/Write**로 manifest에 누락 행 추가

## commands
```powershell
Get-ChildItem ingestion\outputs\jsonl -Filter *.jsonl | Sort-Object LastWriteTime -Descending | Select-Object -First 10 Name, Length, LastWriteTime
# sha256 (값 기록용, 앞 16자만)
Get-FileHash ingestion\outputs\jsonl\<file>.jsonl -Algorithm SHA256 | Select-Object Hash
```

## failure conditions
- raw payload/기사 본문 전문을 manifest에 복사 → BLOCKED_BY_POLICY
- secret/키 값이 manifest에 포함 → BLOCKED_BY_POLICY

## success criteria
- 신규 artifact가 모두 manifest에 1행씩 반영
- 원문 전문 복사 0건, secret 기록 0건

## safety constraints
- 원문 전문(기사 body 전체) 복사 금지 — 경로/해시/메타만
- .env 키 값 기록 금지
- JSONL 등 outputs 파일을 직접 편집 금지 (읽기만)
- git push 금지 / rm·Remove-Item 금지

## output format
```
added_rows: [artifact_path, ...]
manifest_lines_before/after: N -> M
copyright_full_text_copied: 0
secrets_recorded: 0
```
