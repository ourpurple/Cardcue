FROM python:3.11-slim

WORKDIR /app

# Install system utilities, PostgreSQL client libraries, and build tools
# needed for compiling native wheels on aarch64 if pre-built wheels are unavailable.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    libpq-dev \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging configuration and install package
COPY pyproject.toml .
COPY cardcue_api cardcue_api
COPY alembic.ini .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Copy remaining files
COPY . .

# Ensure storage directory exists
RUN mkdir -p /app/data/mail_storage

EXPOSE 8000

CMD ["uvicorn", "cardcue_api.main:app", "--host", "0.0.0.0", "--port", "8000"]