# Preduit backend — the live FastAPI app and forecast pipeline (backend-ai/).
# Build context is the repository root.
FROM python:3.12-slim

# OpenMP for CatBoost, build tools for any source wheels, curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FORECASTER_API_RELOAD=false

# The app finds its data relative to its own folder (data/, output/, .env), so the code
# lives at /app/backend-ai and the volumes mount beneath it.
WORKDIR /app/backend-ai

COPY backend-ai/requirements-runtime.txt ./
RUN pip install -r requirements-runtime.txt

COPY backend-ai/ ./

# Serving database, Joolan source export, history store and saved pipeline outputs.
RUN mkdir -p data output
VOLUME ["/app/backend-ai/data", "/app/backend-ai/output"]

EXPOSE 4000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:4000/health || exit 1

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "4000"]
