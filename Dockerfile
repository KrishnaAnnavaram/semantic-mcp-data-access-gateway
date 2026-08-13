# The backend: quant agent, knowledge retrieval, and the /chat API.
#
# It also carries the MCP servers, because the backend launches them as stdio
# child processes inside this container — they are not separate images. Postgres
# and Qdrant run from their own images; see docker-compose.yml.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The three distributions, each installed editable so imports resolve the same
# way they do in a developer checkout.
COPY .claude/src/postgres/ ./src/postgres/
COPY .claude/src/mcp/ ./src/mcp/
COPY .claude/src/backend/ ./src/backend/
RUN pip install --no-cache-dir -e ./src/postgres -e ./src/mcp -e ./src/backend

# Knowledge corpus, ingested into the vector store on first boot.
COPY knowledge/ ./knowledge/
COPY docs/ ./docs/

# docker-compose.yml is a repo-root marker for treasury_db.paths.repo_root(),
# which walks up looking for one. Without it the container cannot locate /app.
COPY docker-compose.yml ./

ENV PYTHONUNBUFFERED=1 \
    QDRANT_URL=http://qdrant:6333 \
    DATA_BACKEND=mcp

EXPOSE 8000
CMD ["uvicorn", "backend.api.service:app", "--host", "0.0.0.0", "--port", "8000"]
