FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY main.py ./

# Run migrations then start the app
CMD ["/bin/sh", "-c", "uv run alembic upgrade head && uv run python main.py"]
