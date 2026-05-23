FROM python:3.11-slim

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
COPY requirements/worker.txt requirements/worker.txt
COPY requirements/collector.txt requirements/collector.txt
RUN pip install --no-cache-dir -r requirements/worker.txt -r requirements/collector.txt

COPY backend/app/schemas/ backend/app/schemas/
COPY backend/app/db/ backend/app/db/
COPY backend/app/core/ backend/app/core/
COPY backend/app/__init__.py backend/app/__init__.py
COPY workers/ workers/

ENV PYTHONPATH=/app

CMD ["python", "-m", "workers.queue.consumer"]
