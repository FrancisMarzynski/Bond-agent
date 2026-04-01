FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency manifests first — layer cached until deps change
COPY pyproject.toml uv.lock ./

# Install only third-party dependencies (skip the project itself)
# This layer is cached as long as pyproject.toml/uv.lock don't change
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY bond/ ./bond/
COPY setup_db.py ./

# Install the project itself (fast — deps already cached above)
RUN uv sync --frozen --no-dev --no-editable

# Create data directory (SQLite DBs and volumes mounted here)
RUN mkdir -p /app/data

# Expose API port
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "bond.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
