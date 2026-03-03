from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..utils import models
from ..utils.database import get_db
from ..utils.deps import require_auth

router = APIRouter(prefix="/users")


# ---------------------------------------------------------------------------
# GET /users/fetch/display
# ---------------------------------------------------------------------------
@router.get("/fetch/display")
async def fetch_display_name(
    uid: str = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return the current user's display name as a plain HTML text node."""

    user = db.scalars(select(models.User).where(models.User.uid == uid)).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return HTMLResponse(user.display_name)
