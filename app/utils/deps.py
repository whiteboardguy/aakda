"""
deps.py — Shared FastAPI dependencies.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .database import get_db
from .sessions import session_is_valid


def require_auth(request: Request, db: Session = Depends(get_db)) -> str:
    """Dependency that validates the session and returns the authenticated uid.

    Raises HTTP 401 if the session is missing or invalid.
    FastAPI caches get_db per-request, so routes that also declare
    `db: Session = Depends(get_db)` will share the same Session instance.
    """
    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return uid
