import asyncio
from sqlalchemy import select, update
from typing import Annotated
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session, attributes

import json

from ..utils import schemas, models
from ..utils.database import get_db
from ..utils.print_utils import printStat
from ..utils.sessions import session_is_valid

from ..utils.sandbox.sandbox import fetch_graph



router = APIRouter(prefix = "/conversations")


@router.post("/new")
async def create_conversation(
        request: Request,
        user_input: Annotated[schemas.Conversation_Create_Request, Form()],
        db: Session = Depends(get_db),
        ):

    if not request.session['session_id']:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You have to be logged in to create a conversation.")

    if not session_is_valid(request.session['uid'], request.session['session_id'], db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You have to be logged in to create a conversation.")

    new_user_message = schemas.U_msg(message=user_input.initial_query, message_index=1)


    new_conversation = models.Conversation(
            user_uid=request.session['uid'],
            user_messages=[{'message':user_input.initial_query, 'message_index':1}],
            bot_messages=[],
            title=user_input.initial_query[:40]
            )

    db.add(new_conversation)
    db.commit()
    db.refresh(new_conversation)


    result = await asyncio.to_thread(
        fetch_graph,
        query         = user_input.initial_query,
        user_messages = new_conversation.user_messages,
        bot_messages  = new_conversation.bot_messages,
        opt_web       = user_input.opt_web,
        model         = user_input.model,
        timeout       = 300,
        on_status     = lambda msg: print(f"[STATUS] {msg}"),
    ) 

    new_conversation.bot_messages = [result]
    attributes.flag_modified(new_conversation, "bot_messages")
    db.commit()
    db.refresh(new_conversation)

    return new_conversation
