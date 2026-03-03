import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cfg import settings
from .database import engine
from . import models
from .print_utils import printStat


# ---------------------------------------------------------------------------
# Conversation purge
# ---------------------------------------------------------------------------


async def _purge_once(delete_after_days: int) -> None:
    """Hard-delete soft-deleted conversations from the database.

    If delete_after_days is 0, all rows with deleted=True are removed.
    If delete_after_days > 0, only rows whose deleted_at is older than
    that many days are removed.
    """
    now = datetime.now(timezone.utc)

    try:
        with Session(engine) as db:
            query = select(models.Conversation).where(
                models.Conversation.deleted == True  # noqa: E712
            )

            if delete_after_days > 0:
                cutoff = now - timedelta(days=delete_after_days)
                query = query.where(models.Conversation.deleted_at <= cutoff)

            conversations = db.scalars(query).all()

            if not conversations:
                printStat("o", "Purge: no conversations to delete.")
                return

            for conv in conversations:
                db.delete(conv)

            db.commit()
            printStat(
                "o",
                f"Purge: permanently deleted {len(conversations)} conversation(s).",
            )
    except Exception as e:
        printStat("c", f"Purge: error during conversation purge — {e}")


async def run_purge_loop() -> None:
    """Background task that periodically hard-deletes soft-deleted conversations.

    Behaviour is controlled by settings.opts_delete_after:
      -1  — never purge (return immediately)
       0  — purge every hour
      N>0 — purge once per day at midnight UTC
    """
    delete_after = settings.opts_delete_after

    if delete_after == -1:
        printStat("o", "Purge loop disabled (OPTIONS_PERMADELETE_WAIT_DAYS=-1).")
        return

    # Run once immediately on startup so stale rows are cleared right away.
    await _purge_once(delete_after)

    if delete_after == 0:
        printStat(
            "o",
            "Purge loop started: will hard-delete all soft-deleted rows every hour.",
        )
        while True:
            await asyncio.sleep(3600)
            await _purge_once(0)
    else:
        printStat(
            "o",
            f"Purge loop started: will hard-delete rows older than {delete_after} day(s) at midnight UTC.",
        )
        while True:
            now = datetime.now(timezone.utc)
            tomorrow_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sleep_seconds = (tomorrow_midnight - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
            await _purge_once(delete_after)


# ---------------------------------------------------------------------------
# Session purge — runs every 30 minutes, cleans expired session rows
# ---------------------------------------------------------------------------


async def _purge_sessions_once() -> None:
    """Hard-delete session rows whose expire_at timestamp has passed."""
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as db:
            expired = db.scalars(
                select(models.Session).where(models.Session.expire_at < now)
            ).all()

            if not expired:
                return

            for session in expired:
                db.delete(session)

            db.commit()
            printStat(
                "o",
                f"Session purge: removed {len(expired)} expired session(s).",
            )
    except Exception as e:
        printStat("c", f"Session purge: error — {e}")


async def run_session_purge_loop() -> None:
    """Runs every 30 minutes and removes expired session rows from the database."""
    printStat("o", "Session purge loop started (interval: 30 minutes).")
    # Run immediately on startup.
    await _purge_sessions_once()
    while True:
        await asyncio.sleep(1800)
        await _purge_sessions_once()
