# -------------------------------------------------------------------
# Dockerfile  –  AI Agent Platform  (offline / closed-network build)
# -------------------------------------------------------------------
# Build assumptions:
#   - docker/wheels/   contains pre-downloaded .whl files
#   - docker/cache/    contains pre-downloaded tokenizer caches etc.
# Build command (from repo root):
#   docker build -f docker/Dockerfile -t ai-agent-platform:latest .
# -------------------------------------------------------------------

FROM python:3.11-slim AS base

# --- System packages (must be bundled in the base image or pre-cached) ---
# Install Japanese CJK fonts for PDF/Office document generation,
# and minimal build tools. In an offline environment the base image
# must already include these packages; the RUN apt-get commands below
# are kept for reference and work when the registry is accessible.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# --- Telemetry / phone-home disable flags (NFR-002) ---
ENV STRANDS_DISABLE_TELEMETRY=true \
    DO_NOT_TRACK=1 \
    ANONYMIZED_TELEMETRY=false \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TIKTOKEN_CACHE_DIR=/app/cache/tiktoken \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- Install Python dependencies from pre-downloaded wheels (offline) ---
COPY docker/wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt

# --- Copy pre-built tokenizer / model caches ---
COPY docker/cache /app/cache

# --- Copy application source ---
COPY core/       /app/core/
COPY agents/     /app/agents/
COPY integrations/ /app/integrations/

# --- Expose API port ---
EXPOSE 8000

# --- Entrypoint ---
CMD ["python", "-m", "uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000"]
