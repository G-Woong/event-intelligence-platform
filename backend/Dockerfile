FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
COPY requirements/serve.txt requirements/serve.txt
COPY requirements/vector.txt requirements/vector.txt
COPY requirements/worker.txt requirements/worker.txt
COPY requirements/collector.txt requirements/collector.txt
RUN pip install --no-cache-dir -r requirements/serve.txt -r requirements/vector.txt -r requirements/worker.txt -r requirements/collector.txt

COPY backend/ backend/
COPY workers/ workers/
# backend.app.services.semantic_identity_adjudicator → ingestion.orchestration.cross_source_dedup
# (결정적 토큰 헬퍼) 전이 의존. 미COPY 시 semantic adjudication 경로(event_ingest_pipeline·
# semantic-backfill-scheduler)가 런타임 ModuleNotFoundError 로 죽는다(ADR#53 docker dry-run 발견).
COPY ingestion/ ingestion/

# STEP 008B: ensure new alembic revisions invalidate cache
ARG CACHEBUST=0
COPY backend/alembic/versions/ backend/alembic/versions/

COPY backend/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENV PYTHONPATH=/app

ENTRYPOINT ["/app/entrypoint.sh"]
