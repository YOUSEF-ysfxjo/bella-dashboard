FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (layer cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Copy source
COPY . .

# Google token file will be mounted as a volume in docker-compose
# credentials.json must be provided before first run

EXPOSE 3001

CMD ["uv", "run", "python", "server.py"]
