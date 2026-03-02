import uuid
from fastapi.responses import HTMLResponse
import asyncio
from sqlalchemy import select, update
from typing import Annotated
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session, attributes

from uuid import UUID

from itertools import zip_longest

import json

from ..utils import schemas, models
from ..utils.database import get_db
from ..utils.print_utils import printStat
from ..utils.sessions import session_is_valid
from ..cfg import settings

from ..utils.sandbox.sandbox import fetch_graph


router = APIRouter(prefix="/opts")


@router.post("/share/{conv_id}")
async def fetch_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):

    """
    Enable conversation sharing of one's conversation.
    """

    if not request.session["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to modify a conversation.",
        )

    if not session_is_valid(request.session["uid"], request.session["session_id"], db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to modify a conversation.",
        )

    conversation = db.scalars(
        select(models.Conversation)
        .where(
            (models.Conversation.uid == conv_id) &
            (models.Conversation.user_uid == request.session['uid'])
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")


    
    conversation.shared = True   
    conversation.shared_link = str(uuid.uuid4())


    db.commit()
    db.refresh(conversation)

    return f"{settings.aakda_url}/conversations/s/{conversation.shared_link}"



@router.post("/unshare/{conv_id}")
async def fetch_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):

    """
    Disable conversation sharing of one's conversation.
    """

    if not request.session["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to modify a conversation.",
        )

    if not session_is_valid(request.session["uid"], request.session["session_id"], db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to modify a conversation.",
        )

    conversation = db.scalars(
        select(models.Conversation)
        .where(
            (models.Conversation.uid == conv_id) &
            (models.Conversation.user_uid == request.session['uid'])
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    
    conversation.shared = False   
    conversation.shared_link = ""


    db.commit()
    db.refresh(conversation)

    return status.HTTP_200_OK




@router.post("/delete/{conv_id}")
async def delete_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):

    """
    Enable conversation deleting of one's conversation.
    """

    if not request.session["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to delete a conversation.",
        )

    if not session_is_valid(request.session["uid"], request.session["session_id"], db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to delete a conversation.",
        )

    conversation = db.scalars(
        select(models.Conversation)
        .where(
            (models.Conversation.uid == conv_id) &
            (models.Conversation.user_uid == request.session['uid'])
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    
    conversation.deleted = True   


    db.commit()
    db.refresh(conversation)

    return status.HTTP_204_NO_CONTENT
