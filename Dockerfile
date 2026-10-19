# Preduit backend — FastAPI serving app + ML pipeline (preduit-engine + preduit-app)
# Build context is the repository root so both packages are available.
FROM python:3.12-slim

# System libraries: OpenMP for CatBoost, build tools + gfortran for any source builds,
# curl for the container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Serve data from a mounted volume rather than the legacy backend-ai/ path.
    FORECASTER_DB_PATH=/data/forecast.db \
    FORECASTER_OUTPUT_DIR=/data/output \
    FORECASTER_API_HOST=0.0.0.0 \
    FORECASTER_API_PORT=4000 \
    FORECASTER_API_RELOAD=false

WORKDIR /app

# Install the two Python packages (engine first — the app depends on it).
COPY preduit-engine/ ./preduit-engine/
COPY preduit-app/ ./preduit-app/
RUN pip install ./preduit-engine ./preduit-app

# Data / DB / outputs live on a volume so they survive container restarts.
RUN mkdir -p /data/output
VOLUME ["/data"]

EXPOSE 4000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:4000/health || exit 1

# Reload is forced off for production images.
CMD ["uvicorn", "preduit_app.api_server:app", "--host", "0.0.0.0", "--port", "4000"]
