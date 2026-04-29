FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/.venv/bin:$PATH"

# Install uv
RUN pip install --no-cache-dir uv

# Create non-root runtime user early so source copies can carry final ownership
RUN groupadd --system bond && \
    useradd --system --gid bond --home-dir /app bond

# Copy dependency manifests first — layer cached until deps change
COPY pyproject.toml uv.lock ./

# Install only third-party dependencies (skip the project itself)
# This layer is cached as long as pyproject.toml/uv.lock don't change
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY --chown=bond:bond bond/ ./bond/
COPY --chown=bond:bond setup_db.py ./

# Install the project itself (fast — deps already cached above)
RUN uv sync --frozen --no-dev --no-editable

# Create writable mountpoint for runtime state, including model caches
RUN mkdir -p /app/data/.cache/huggingface /app/data/.cache/sentence-transformers && \
    chown -R bond:bond /app/data

ENV HF_HOME=/app/data/.cache/huggingface
ENV HUGGINGFACE_HUB_CACHE=/app/data/.cache/huggingface/hub
ENV TRANSFORMERS_CACHE=/app/data/.cache/huggingface/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/app/data/.cache/sentence-transformers
ENV HF_HUB_DISABLE_XET=1

# Expose API port
EXPOSE 8000

USER bond

CMD ["uvicorn", "bond.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
