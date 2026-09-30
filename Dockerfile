FROM python:3.12-slim-bookworm AS backend
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend/generated
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY proto proto
COPY scripts/generate.py scripts/generate.py
RUN python scripts/generate.py
COPY backend backend
COPY ai/validation.py ai/validation.py
CMD ["sh", "-c", "if [ ! -f \"$USERS_PATH\" ]; then python -m backend.seed_users --demo --output \"$USERS_PATH\"; fi && exec python -m backend.server"]

FROM python:3.12-slim-bookworm AS ai-build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake && rm -rf /var/lib/apt/lists/*
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_METAL=OFF" CMAKE_BUILD_PARALLEL_LEVEL=2
COPY ai/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS ai
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=ai-build /usr/local /usr/local
COPY --from=backend /app/backend/generated backend/generated
COPY ai ai
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend/generated HF_HOME=/models
CMD ["python", "-m", "ai.server"]

FROM node:24-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
COPY proto /app/proto
RUN npm run build && npm run lint

FROM nginx:1.28-alpine AS web
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
