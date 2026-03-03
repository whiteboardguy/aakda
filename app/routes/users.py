from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..utils import models
from ..utils.database import get_db
from ..utils.sessions import session_is_valid

router = APIRouter(prefix="/users")


# ---------------------------------------------------------------------------
# GET /users/fetch/display
# ---------------------------------------------------------------------------
@router.get("/fetch/display")
async def fetch_display_name(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the current user's display name as a plain HTML text node."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.scalars(select(models.User).where(models.User.uid == uid)).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return HTMLResponse(user.display_name)
