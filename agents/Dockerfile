FROM python:3.11-slim

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
COPY requirements/ai.txt requirements/ai.txt
COPY requirements/worker.txt requirements/worker.txt
RUN pip install --no-cache-dir -r requirements/ai.txt -r requirements/worker.txt

COPY backend/app/schemas/ backend/app/schemas/
COPY backend/app/services/llm_client.py backend/app/services/llm_client.py
COPY backend/app/db/ backend/app/db/
COPY backend/app/core/ backend/app/core/
COPY backend/app/__init__.py backend/app/__init__.py
COPY backend/app/services/__init__.py backend/app/services/__init__.py
COPY agents/ agents/
COPY workers/pipelines/ workers/pipelines/
COPY workers/__init__.py workers/__init__.py

ENV PYTHONPATH=/app
ENV BACKEND_URL=http://backend:8000

CMD ["python", "-m", "agents.agent_worker"]
