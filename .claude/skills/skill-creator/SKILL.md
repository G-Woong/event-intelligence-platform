---
name: skill-creator
description: Claude Code skill을 저작·평가·벤치마킹할 때 사용. 신규 skill을 만들거나, 기존 6종(test-validation/docs-sync/source-audit/runner-contract/artifact-manifest/turn-closeout)의 description 트리거 정확도를 train/test로 측정·개선하거나, with/without A/B로 효용을 정량화할 때. 다른 신규 skill 도입 품질의 검증 게이트.
license: Apache-2.0 (upstream)
upstream: https://github.com/anthropics/skills/tree/main/skills/skill-creator
adapted_for: WEB_INTELLIGENCE_HARNESS_EVOLUTION.md S1
---

# skill-creator (메타-skill: 하네스 품질 정량화)

> upstream `anthropics/skills/skill-creator`(Apache-2.0)를 본 프로젝트로 분해·적응. 하네스 자체를
> "개선되는 시스템"으로 만든다. **다른 4개 신규 skill(S2~S5) 도입 품질도 이 skill로 검증**한다.

## 언제 쓰나
- 신규 skill을 만들 때(프론트매터·description·구조 설계).
- 기존/신규 skill의 **트리거 정확도**가 의심될 때(발화해야 할 때 안 하거나, 과발화).
- skill 도입 전후 효용을 수치로 비교할 때(with_skill vs without_skill).

## 절차
1. **대상 정의:** 평가할 skill과 그 description을 수집(`.claude/skills/*/SKILL.md` 프론트매터).
2. **트리거 케이스 구성:** 발화해야 하는 프롬프트(positive) N개 + 발화 안 해야 하는(negative) N개. 60/40 train/test 분리.
3. **측정:** test 셋에서 정확도/오발화율 산출(수동 또는 보조 스크립트).
4. **개선:** description을 좁히거나 트리거 키워드를 보강 → 재측정(루프).
5. **A/B:** 동일 과제를 with/without로 실행해 산출물 품질·턴 수 비교.
6. **기록:** 결과를 PROJECT_STATUS/_DECISIONS에 요약(turn-closeout 경유).

## 안전·제약
- 파일시스템 내부만. 외부 호출 0. `.env` 미열람. `rm`/`Remove-Item` 금지(정리는 `Move-Item`).
- 기존 6종과 **비중복**(메타-레벨). turn-closeout의 stamp 로직을 건드리지 않는다.

## 후속(선택 벤더링)
- upstream `scripts/{run_loop,package_skill,aggregate_benchmark}.py`를 본 디렉터리로 가져와 경로만 적응하면 자동화 루프 가능(현재는 가이드 형태로 적용; 스크립트 벤더링은 별도 atomic task).
