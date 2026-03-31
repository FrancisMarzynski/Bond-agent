FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into the system Python (no venv inside container)
RUN uv sync --frozen --no-dev --no-editable

# Copy application source
COPY bond/ ./bond/
COPY setup_db.py ./

# Create data directory (volumes will be mounted here)
RUN mkdir -p /app/data

# Expose API port
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "bond.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
