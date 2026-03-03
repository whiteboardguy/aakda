import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from ..cfg import settings
from ..utils import models
from ..utils.database import get_db
from ..utils.print_utils import printStat
from ..utils.sessions import session_is_valid
from ..utils.templating import templates


router = APIRouter(prefix="/opts")


def _build_conv_context(conv: models.Conversation) -> dict:
    """Build the template context dict for a sidebar_item.html render."""
    return {
        "conv": {
            "uuid": str(conv.uid),
            "title": (
                conv.user_messages[0]["message"][:40]
                if conv.user_messages
                else "Untitled"
            ),
            "updated_at": conv.updated_at,
            "shared": conv.shared,
            "shared_link": conv.shared_link,
        }
    }


@router.post("/share/{conv_id}")
async def share_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Enable sharing for a conversation; return updated sidebar item."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.uid == conv_id) & (models.Conversation.user_uid == uid)
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.shared = True
    conversation.shared_link = str(uuid.uuid4())
    db.commit()
    db.refresh(conversation)

    return templates.TemplateResponse(
        "partials/sidebar_item.html",
        {"request": request, **_build_conv_context(conversation)},
        headers={"X-Share-Link": conversation.shared_link},
    )


@router.post("/unshare/{conv_id}")
async def unshare_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Disable sharing for a conversation; return updated sidebar item."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.uid == conv_id) & (models.Conversation.user_uid == uid)
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.shared = False
    conversation.shared_link = ""
    db.commit()
    db.refresh(conversation)

    return templates.TemplateResponse(
        "partials/sidebar_item.html",
        {"request": request, **_build_conv_context(conversation)},
    )


@router.post("/delete/{conv_id}")
async def delete_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Soft-delete a conversation; return empty HTML so htmx removes the sidebar item."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.uid == conv_id) & (models.Conversation.user_uid == uid)
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.deleted = True
    conversation.deleted_at = datetime.now(timezone.utc)
    db.commit()

    # Empty response — htmx outerHTML swap removes the element from the DOM.
    return HTMLResponse("")
