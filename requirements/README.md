# requirements/

용도별 분리 의존성 매니페스트.

## 레이아웃
| 파일 | 목적 |
|---|---|
| `base.txt` | 모든 환경 공통 코어 (HTTP, 직렬화, 유틸, 관측) |
| `serve.txt` | FastAPI API 서버 런타임 |
| `worker.txt` | Celery/RQ 비동기 워커 런타임 |
| `ai.txt` | LangChain / LangGraph / OpenAI / LlamaIndex |
| `ml.txt` | torch / transformers / sentence-transformers / 로컬 LLM |
| `crawler.txt` | playwright / selenium / 파서 / 피드 / 소셜 |
| `vector.txt` | pymilvus + lancedb (벡터 스토어) |
| `dev.txt` | pytest / ruff / mypy / Jupyter |

## 설치 (uv 권장)
```powershell
# API + AI + Vector
uv pip install -r requirements\serve.txt -r requirements\ai.txt -r requirements\vector.txt

# 워커
uv pip install -r requirements\worker.txt -r requirements\ai.txt -r requirements\crawler.txt

# 개발 도구
uv pip install -r requirements\dev.txt
```

## 주의
- 본 단계에서는 **아무 것도 설치하지 않는다.** 파일 정의만 한다.
- 실제 설치 정책 / GPU 휠 인덱스 / 컨테이너 이미지 레이어링은 다음 단계에서 확정한다.
- 원본 단일 핀 파일 `../requirements.txt`는 reference로 유지한다.
- `pymilvus==2.4.4` 호환을 위해 `setuptools<81`을 `vector.txt`에서 명시적으로 핀했다.
