FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
COPY requirements/serve.txt requirements/serve.txt
COPY requirements/vector.txt requirements/vector.txt
COPY requirements/worker.txt requirements/worker.txt
RUN pip install --no-cache-dir -r requirements/serve.txt -r requirements/vector.txt -r requirements/worker.txt

COPY backend/ backend/
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENV PYTHONPATH=/app

ENTRYPOINT ["/app/entrypoint.sh"]
