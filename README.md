# aakda

AI-powered interactive graph maker. FastAPI + PostgreSQL + Uvicorn, containerised with Docker Compose.

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- [uv](https://github.com/astral-sh/uv) (for local dev outside Docker)
- Python 3.14+

---

## Running with Docker (recommended)

```bash
cp .env.example .env
# fill in .env — at minimum: LLM_API_KEY, JINA_API_KEY, DATABASE_PASSWORD, SECURITY_SESSION_SECRET
docker compose up -d
```

The app will be available at `http://localhost:${INSTANCE_PORT}` (default `5000`).

Migrations run automatically on container start via `alembic upgrade head`.

---

## Running locally (no Docker)

```bash
cp .env.example .env
# set DATABASE_HOSTNAME=localhost in .env

uv sync
uv run alembic upgrade head
uv run python main.py
```

Requires a running PostgreSQL instance matching the `DATABASE_*` vars in `.env`.

---

## Environment variables

Copy `.env.example` to `.env` and fill in the required values. Key variables:

| Variable | Required | Description |
|---|---|---|
| `LLM_BASE_URL` | Yes | OpenAI-compatible API base URL |
| `LLM_API_KEY` | Yes | API key for the LLM provider |
| `LLM_MODEL` | Yes | Model ID (e.g. `openai/gpt-4o`) |
| `JINA_API_KEY` | Yes | Jina AI API key (used for web tool) |
| `DATABASE_*` | Yes | PostgreSQL connection details |
| `SECURITY_SESSION_SECRET` | Yes | Secret for session signing — generate with `python -c "import secrets; print(secrets.token_hex(64))"` |
| `INSTANCE_PORT` | No | Port to bind (default `5000`) |
| `OPTIONS_WORKERS` | No | Uvicorn worker count (default `1`) |
| `OPTIONS_AUTOVERIFY` | No | Auto-verify new users without email flow (default `false`) |
| `DEBUG` | No | Enables hot-reload, exposes `/docs` (default `false`) |

---

## Database migrations

```bash
# generate a new migration after model changes
uv run alembic revision --autogenerate -m "describe change"

# apply pending migrations
uv run alembic upgrade head

# downgrade one step
uv run alembic downgrade -1
```

---

## Tests

```bash
uv sync --group dev
uv run pytest
```

Tests use an in-memory SQLite DB. No real DB or LLM calls are made.

---

## Health check

`GET /healthz` — returns `{"status": "ok"}` with HTTP 200. Used by Docker Compose and any upstream load balancer.
