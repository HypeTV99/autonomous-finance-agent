FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schemas.py tax_engine.py compliance_engine.py firestore_store.py \
     razorpayx_client.py slack_service.py vertex_agent.py benchmark_suite.py main.py ./
COPY services/ ./services/
COPY static/ ./static/
COPY mock/ ./mock/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
