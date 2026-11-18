FROM python:3.12-slim-bookworm AS python-base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/backend/generated
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY proto proto
COPY scripts/generate_protos.py scripts/generate_protos.py
RUN python scripts/generate_protos.py

FROM python-base AS backend
COPY backend backend
COPY ai/validation.py ai/validation.py
COPY scripts/raft_status.py scripts/raft_status.py
CMD ["python", "-m", "backend.server"]

FROM python-base AS ai
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake && rm -rf /var/lib/apt/lists/*
COPY ai/requirements.txt ai/requirements.txt
RUN CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_BLAS=OFF" CMAKE_BUILD_PARALLEL_LEVEL=2 pip install --no-cache-dir -r ai/requirements.txt
COPY ai ai
CMD ["python", "-m", "ai.server"]
