"""LLM AUTO-GENERATED TEST
conftest.py — shared pytest fixtures for the Aakda test suite.

Strategy:
- All env vars are set to fake values before any app module is imported,
  so cfg.py doesn't sys.exit().
- app.utils.models is imported first so all ORM tables register with
  Base.metadata before we hand the metadata to SQLite.
- PostgreSQL-specific server_defaults that SQLite can't execute
  (now(), NOW() + INTERVAL) are patched to SQLite-compatible equivalents
  using DefaultClause before create_all is called.
- A sqlite:///memory engine with StaticPool is used so all connections
  share the same in-memory database.
- FastAPI's dependency_overrides replaces get_db with the SQLite session.
- The slowapi rate limiter is reset between tests so limits don't bleed
  across test functions.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import DefaultClause
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator
from sqlalchemy.sql.sqltypes import TIMESTAMP


class _SQLiteUUID(TypeDecorator):
    """UUID stored as VARCHAR(36), accepts both str and uuid.UUID objects."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value)


class _SQLiteTZTimestamp(TypeDecorator):
    """TIMESTAMP stored as TEXT; result is always timezone-aware (UTC)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            # Already a datetime (shouldn't happen with String impl, but guard)
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        # Parse ISO string from SQLite
        from datetime import datetime as _dt

        try:
            # Handle 'YYYY-MM-DD HH:MM:SS.ffffff' format from SQLite
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    parsed = _dt.strptime(value, fmt)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except ValueError:
                    continue
        except Exception:
            pass
        return value


from sqlalchemy.types import TypeDecorator

# ---------------------------------------------------------------------------
# 1. Set required env vars BEFORE any app import
# ---------------------------------------------------------------------------
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "http://localhost")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("JINA_API_KEY", "test-jina")
os.environ.setdefault("DATABASE_HOSTNAME", "test-db-does-not-exist")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_PASSWORD", "test")
os.environ.setdefault("DATABASE_NAME", "test")
os.environ.setdefault("DATABASE_USERNAME", "test")
os.environ.setdefault("SECURITY_SESSION_SECRET", "testsecretkey1234567890abcdefgh")
os.environ.setdefault("INSTANCE_URL", "http://localhost:5000")
os.environ.setdefault("INSTANCE_HOST", "0.0.0.0")
os.environ.setdefault("INSTANCE_PORT", "5000")
os.environ.setdefault("OPTIONS_AUTOVERIFY", "true")
os.environ.setdefault("DEBUG", "false")

# ---------------------------------------------------------------------------
# 2. Import models to register tables with Base.metadata, then patch
#    PostgreSQL-specific server_defaults to SQLite-compatible equivalents.
# ---------------------------------------------------------------------------
import app.utils.models  # noqa: E402 — must come after env vars are set
from app.utils.models import Conversation, Session as SessionModel, User
from app.utils.database import Base


def _patch_server_defaults():
    """Replace PostgreSQL SQL expressions in server_defaults with SQLite equivalents."""
    sqlite_now = DefaultClause(text("CURRENT_TIMESTAMP"))
    sqlite_expire = DefaultClause(text("datetime('now', '+7 days')"))

    for col in User.__table__.c:
        if col.server_default and "now()" in str(col.server_default.arg).lower():
            col.server_default = sqlite_now

    for col in Conversation.__table__.c:
        if col.server_default and "now()" in str(col.server_default.arg).lower():
            col.server_default = sqlite_now

    SessionModel.__table__.c.expire_at.server_default = sqlite_expire


def _patch_uuid_types():
    """Replace postgresql UUID and TIMESTAMP(tz) column types with SQLite-compatible
    equivalents that handle str/uuid.UUID values and timezone-aware datetimes."""
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy.sql.sqltypes import TIMESTAMP

    for table in Base.metadata.tables.values():
        for col in table.c:
            if isinstance(col.type, PG_UUID):
                col.type = _SQLiteUUID()
            elif isinstance(col.type, TIMESTAMP):
                col.type = _SQLiteTZTimestamp()


_patch_server_defaults()
_patch_uuid_types()

# ---------------------------------------------------------------------------
# 3. Build a module-level SQLite engine (StaticPool = single shared connection)
# ---------------------------------------------------------------------------
_sqlite_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_sqlite_engine)


def _override_get_db():
    with OrmSession(_sqlite_engine) as session:
        yield session


# ---------------------------------------------------------------------------
# 4. Import the FastAPI app and wire up the DB override.
#    aakda.py no longer calls create_all, so no mock needed.
# ---------------------------------------------------------------------------
from app.aakda import app  # noqa: E402
from app.utils.database import get_db  # noqa: E402

app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# 5. Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_db():
    """Wipe all rows between tests so each test starts with an empty database."""
    yield
    with OrmSession(_sqlite_engine) as s:
        s.query(SessionModel).delete()
        s.query(Conversation).delete()
        s.query(User).delete()
        s.commit()


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Clear the in-memory rate-limit storage between tests."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture
def client():
    """A TestClient that does NOT follow redirects (so we can assert 302 locations)."""
    with TestClient(app, raise_server_exceptions=True, follow_redirects=False) as c:
        yield c


# ---------------------------------------------------------------------------
# 6. Seed helpers
# ---------------------------------------------------------------------------


def make_user(
    username: str = "testuser",
    display_name: str = "Test User",
    email: str = "test@example.com",
    password: str = "password123",
) -> User:
    """Insert a User row (password stored as plain text — tests don't care about hashing)."""
    from app.utils.utils import hash as hash_pwd

    with OrmSession(_sqlite_engine) as s:
        user = User(
            uid=uuid.uuid4(),
            username=username,
            display_name=display_name,
            email=email,
            password=hash_pwd(password),
            verified=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        # Detach from session so caller can use the object freely
        return User(
            uid=user.uid,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            password=user.password,
            verified=user.verified,
        )


def make_session(user: User) -> str:
    """Insert a Session row and return the session_id string."""
    sid = uuid.uuid4()
    with OrmSession(_sqlite_engine) as s:
        sess = SessionModel(
            session_id=sid,
            user_uid=user.uid,
            expire_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        s.add(sess)
        s.commit()
    return str(sid)


def auth_cookies(
    client: TestClient, username: str = "testuser", password: str = "password123"
) -> None:
    """Log in via the API and set the session cookie on the client instance.

    Starlette's SessionMiddleware requires the cookie to be set at the client
    level (not per-request) so that subsequent requests carry it correctly.
    After calling this helper the client is authenticated for all future requests
    until the cookies are cleared.
    """
    r = client.post(
        "/auth/users/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    # The session cookie is already set on the client by TestClient after the
    # request completes — no manual cookie propagation needed.


def make_conversation(user: User, title: str = "Test conv") -> Conversation:
    """Insert a Conversation row directly into the DB."""
    with OrmSession(_sqlite_engine) as s:
        conv = Conversation(
            uid=uuid.uuid4(),
            user_uid=user.uid,
            title=title,
            user_messages=[{"message": title, "message_index": 1}],
            bot_messages=[],
            deleted=False,
            shared=False,
            locked_state=False,
        )
        s.add(conv)
        s.commit()
        s.refresh(conv)
        uid = conv.uid
    # Re-fetch in a fresh session to return a clean detached-ish object
    with OrmSession(_sqlite_engine) as s:
        return s.get(Conversation, (uid, user.uid))
