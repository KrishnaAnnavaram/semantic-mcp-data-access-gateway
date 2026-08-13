# Layer 2 — the smart agent /chat service.
# (The data layer runs Postgres from an image; this image is the reasoning API.)
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Product code + knowledge docs (ingested into the vector store on first boot).
COPY src/ ./src/
COPY knowledge/ ./knowledge/

ENV PYTHONUNBUFFERED=1 \
    QDRANT_URL=http://qdrant:6333 \
    DATA_BACKEND=postgres

WORKDIR /app/src
EXPOSE 8000
CMD ["uvicorn", "agent_service:app", "--host", "0.0.0.0", "--port", "8000"]
