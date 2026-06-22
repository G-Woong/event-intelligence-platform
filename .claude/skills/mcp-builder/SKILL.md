---
name: mcp-builder
description: 프로젝트 내부 기능을 MCP 서버 tool로 노출하는 자체 MCP를 설계·구현할 때 사용. ingestion 러너(RSS/HTML/API/Playwright)나 expansion_router를 MCP tool로 래핑해 LangGraph 에이전트가 MCP 클라이언트로 호출하게 만들 때(요구1 LLM 계획층 배선). FastMCP/Pydantic 스키마 + 4단계(리서치→구현→리뷰→eval).
license: Apache-2.0 (upstream)
upstream: https://github.com/anthropics/skills/tree/main/skills/mcp-builder
adapted_for: WEB_INTELLIGENCE_HARNESS_EVOLUTION.md S3
---

# mcp-builder (우리를 MCP 제공자로)

> upstream `anthropics/skills/mcp-builder`(Apache-2.0) 적응. 외부 MCP 5종을 소비하는 동시에,
> 우리 러너를 **MCP tool로 제공**하는 역방향을 연다. runner-contract-skill(출력 검증)과 방향 상이(인터페이스 설계).

## 언제 쓰나
- 결정론 러너/`expansion_router`를 LLM 계획층이 직접 호출 가능한 tool로 노출하고 싶을 때.
- 신규 MCP tool 인터페이스(입력/출력 Pydantic 스키마)를 설계할 때.

## 4단계 절차
1. **리서치:** 노출 대상 함수의 입력/출력/실패모드 정리. 불변 가드(우회금지·전문저장금지·rate gate) 확인.
2. **구현:** FastMCP(Python)로 tool 정의. 입출력은 Pydantic, 비밀은 env(`${VAR}`)만. 부작용 최소.
3. **리뷰:** security-permission-guardian agent로 권한·비밀·파괴면 점검. destructive tool 미노출.
4. **eval:** QA pair(입력→기대출력) 10쌍으로 tool 동작 검증(runner-contract와 연계).

## 안전·제약
- 노출 tool은 **read/계획 보조 한정** 기본. fetch는 기존 결정론 경로(robots/rate 준수) 유지 — 우회 신설 금지.
- 전문 저장 금지·비밀 미노출 불변. WebFetch는 modelcontextprotocol.io 문서 한정.
- 우리 자체 MCP도 `.mcp.json`에 추가 시 `${VAR}` 참조·restricted 기본.
