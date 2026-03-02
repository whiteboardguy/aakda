from . import conv_opts

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

from ..utils.sandbox.sandbox import fetch_graph


router = APIRouter(prefix="/conversations")

router.include_router(conv_opts.router)


@router.post("/new", response_class=HTMLResponse)
async def create_conversation(
    request: Request,
    user_input: Annotated[schemas.Conversation_Create_Request, Form()],
    db: Session = Depends(get_db),
):

    """
    Create a new conversation by passing a query, web-search preference, and preferred model encoded in Form.
    """

    if not request.session["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to create a conversation.",
        )

    if not session_is_valid(request.session["uid"], request.session["session_id"], db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to create a conversation.",
        )

    new_user_message = schemas.U_msg(
        message=user_input.query, message_index=1
    ).model_dump()

    new_conversation = models.Conversation(
        user_uid=request.session["uid"],
        user_messages=[new_user_message],
        bot_messages=[],
        title=user_input.query[:40],
    )

    db.add(new_conversation)
    db.commit()
    db.refresh(new_conversation)

    result = await asyncio.to_thread(
        fetch_graph,
        query=user_input.query,
        user_messages=new_conversation.user_messages,
        bot_messages=new_conversation.bot_messages,
        opt_web=user_input.opt_web,
        model=user_input.model,
        timeout=300,
        on_status=lambda msg: print(f"[STATUS] {msg}"),
    )

    result['message_index'] = 1

    new_conversation.bot_messages = [result]
    attributes.flag_modified(new_conversation, "bot_messages")
    db.commit()
    db.refresh(new_conversation)

    return new_conversation.bot_messages[0]["render_plot_html"]



@router.post("/continue/{conv_id}", response_class=HTMLResponse)
async def continue_conversation(
    conv_id: UUID,
    request: Request,
    user_input: Annotated[schemas.Conversation_Continue_Request, Form()],
    db: Session = Depends(get_db),
):

    """
    Continue an existing conversation by passing a query, web-search preference, and preferred model encoded in Form.
    """

    if not request.session["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to continue a conversation.",
        )

    if not session_is_valid(request.session["uid"], request.session["session_id"], db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to continue a conversation.",
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

    new_message_index = int(conversation.user_messages[-1]['message_index'])+1


    user_message = schemas.U_msg(message=user_input.query, message_index=(new_message_index)).model_dump()

    conversation.user_messages.append(user_message)
    db.commit()


    result = await asyncio.to_thread(
        fetch_graph,
        query=user_input.query,
        user_messages=conversation.user_messages,
        bot_messages=conversation.bot_messages,
        opt_web=user_input.opt_web,
        model=user_input.model,
        timeout=300,
        on_status=lambda msg: print(f"[STATUS] {msg}"),
    )

    result['message_index'] = new_message_index

    conversation.bot_messages.append(result)
    # attributes.flag_modified(conversation, "bot_messages")
    db.commit()
    db.refresh(conversation)

    return conversation.bot_messages[-1]["render_plot_html"]



@router.get("/fetch/{conv_id}")
async def fetch_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):

    """
    Find conversations with their UIDs, given that you own them.
    Shared ones are handled by the '/conversations/shared/{conv_id}' route.
    """

    if not request.session["session_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to fetch this conversation.",
        )

    if not session_is_valid(request.session["uid"], request.session["session_id"], db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You have to be logged in to fetch this conversation.",
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


    interleaved = [x for pair in zip(conversation.user_messages, conversation.bot_messages) for x in pair]

    return interleaved


@router.get("/s/{conv_id}")
async def fetch_shared_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):

    """
    Fetch a shared conversation.
    """

    conversation = db.scalars(
        select(models.Conversation)
        .where(
            (models.Conversation.uid == conv_id) &
            (models.Conversation.shared)
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    interleaved = [x for pair in zip(conversation.user_messages, conversation.bot_messages) for x in pair]

    return interleaved
