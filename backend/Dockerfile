FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
COPY requirements/serve.txt requirements/serve.txt
COPY requirements/vector.txt requirements/vector.txt
COPY requirements/worker.txt requirements/worker.txt
RUN pip install --no-cache-dir -r requirements/serve.txt -r requirements/vector.txt -r requirements/worker.txt

COPY backend/ backend/

ENV PYTHONPATH=/app

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
