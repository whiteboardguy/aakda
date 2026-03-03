import asyncio
import json
import uuid
from datetime import datetime, timezone
from itertools import zip_longest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import not_, select, update
from sqlalchemy.orm import Session, attributes

from . import conv_opts
from ..utils import jobs, models, schemas
from ..utils.database import engine, get_db
from ..utils.print_utils import printStat
from ..utils.sandbox.sandbox import fetch_graph
from ..utils.sessions import session_is_valid
from ..utils.templating import templates

router = APIRouter(prefix="/conversations")
router.include_router(conv_opts.router)


# ---------------------------------------------------------------------------
# Background job: runs fetch_graph off the event loop, persists result,
# emits SSE events.  remove_job is intentionally NOT called here — the SSE
# generator in chat.py owns that responsibility.
# ---------------------------------------------------------------------------
async def _run_job(
    job_id: str,
    conv_uid: str,
    user_uid: str,
    query: str,
    opt_web: bool,
    model: str,
    message_index: int,
    snapshot_user_messages: list,
    snapshot_bot_messages: list,
) -> None:
    queue = jobs.get_job(job_id)
    if queue is None:
        return

    loop = asyncio.get_running_loop()

    def on_status(msg: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "status", "data": msg})

    try:
        result = await asyncio.to_thread(
            fetch_graph,
            query=query,
            user_messages=snapshot_user_messages,
            bot_messages=snapshot_bot_messages,
            opt_web=opt_web,
            model=model,
            timeout=300,
            on_status=on_status,
        )

        result["message_index"] = message_index

        # Persist with an independent DB session and an ownership re-check.
        with Session(engine) as db:
            conversation = db.scalars(
                select(models.Conversation).where(
                    (models.Conversation.uid == conv_uid)
                    & (models.Conversation.user_uid == user_uid)
                    & not_(models.Conversation.deleted)
                )
            ).first()

            if not conversation:
                raise RuntimeError("Conversation not found or access denied")

            conversation.bot_messages.append(result)
            attributes.flag_modified(conversation, "bot_messages")
            conversation.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Normalise any JSON-string fields before rendering.
        bot_msg = dict(result)
        if isinstance(bot_msg.get("sources"), str):
            bot_msg["sources"] = json.loads(bot_msg["sources"])
        if isinstance(bot_msg.get("tools_called"), str):
            bot_msg["tools_called"] = json.loads(bot_msg["tools_called"])

        user_msg_dict = {"message": query, "message_index": message_index}

        html = templates.env.get_template("partials/message_group.html").render(
            {
                "user_msg": user_msg_dict,
                "bot_msg": bot_msg,
                "conv_id": conv_uid,
            }
        )
        queue.put_nowait({"type": "done", "data": html.replace("\n", " ")})

    except Exception as exc:
        printStat("c", f"Background job {job_id} failed: {exc}")
        error_html = templates.env.get_template("partials/error_bubble.html").render(
            {"error_message": str(exc)}
        )
        queue.put_nowait({"type": "error", "data": error_html.replace("\n", " ")})


# ---------------------------------------------------------------------------
# POST /conversations/new
# ---------------------------------------------------------------------------
@router.post("/new")
async def create_conversation(
    request: Request,
    user_input: Annotated[schemas.Conversation_Create_Request, Form()],
    db: Session = Depends(get_db),
):
    """Create a new conversation, spawn background AI job, return SSE listener."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    new_user_message = schemas.U_msg(
        message=user_input.query, message_index=1
    ).model_dump()

    new_conversation = models.Conversation(
        user_uid=uid,
        user_messages=[new_user_message],
        bot_messages=[],
        title=user_input.query[:40],
    )
    db.add(new_conversation)
    db.commit()
    db.refresh(new_conversation)

    conv_uid = str(new_conversation.uid)
    job_id = str(uuid.uuid4())
    q = jobs.create_job(job_id)  # noqa: F841 — queue handed off to background task

    asyncio.create_task(
        _run_job(
            job_id=job_id,
            conv_uid=conv_uid,
            user_uid=uid,
            query=user_input.query,
            opt_web=user_input.opt_web,
            model=user_input.model,
            message_index=1,
            snapshot_user_messages=list(new_conversation.user_messages),
            snapshot_bot_messages=[],
        )
    )

    return templates.TemplateResponse(
        "partials/sse_listener.html",
        {
            "request": request,
            "job_id": job_id,
            "conv_id": conv_uid,
            "query": user_input.query,
            "conv": {
                "uuid": conv_uid,
                "title": user_input.query[:40],
            },
        },
    )


# ---------------------------------------------------------------------------
# POST /conversations/continue/{conv_id}
# ---------------------------------------------------------------------------
@router.post("/continue/{conv_id}")
async def continue_conversation(
    conv_id: UUID,
    request: Request,
    user_input: Annotated[schemas.Conversation_Continue_Request, Form()],
    db: Session = Depends(get_db),
):
    """Continue an existing conversation; spawn background AI job, return SSE listener."""

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

    if not conversation or conversation.deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    new_message_index = int(conversation.user_messages[-1]["message_index"]) + 1

    user_message = schemas.U_msg(
        message=user_input.query, message_index=new_message_index
    ).model_dump()

    conversation.user_messages.append(user_message)
    attributes.flag_modified(conversation, "user_messages")
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Snapshot after appending the new user message.
    snapshot_user = list(conversation.user_messages)
    snapshot_bot = list(conversation.bot_messages)

    conv_uid = str(conv_id)
    job_id = str(uuid.uuid4())
    jobs.create_job(job_id)

    asyncio.create_task(
        _run_job(
            job_id=job_id,
            conv_uid=conv_uid,
            user_uid=uid,
            query=user_input.query,
            opt_web=user_input.opt_web,
            model=user_input.model,
            message_index=new_message_index,
            snapshot_user_messages=snapshot_user,
            snapshot_bot_messages=snapshot_bot,
        )
    )

    return templates.TemplateResponse(
        "partials/sse_listener.html",
        {
            "request": request,
            "job_id": job_id,
            "conv_id": conv_uid,
            "query": user_input.query,
        },
    )


# ---------------------------------------------------------------------------
# GET /conversations/new-form — resets the chat area for a new conversation
# ---------------------------------------------------------------------------
@router.get("/new-form")
async def new_conversation_form(request: Request):
    """Return an empty chat-area placeholder; JS resets the form action to /conversations/new."""
    return HTMLResponse(
        '<div id="chat-area-placeholder" class="flex items-center justify-center h-full">'
        '<p class="text-base-content/40 text-sm select-none">Ask anything to start a new conversation.</p>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# GET /conversations/fetch/{conv_id}
# ---------------------------------------------------------------------------
@router.get("/fetch/{conv_id}")
async def fetch_conversation(
    conv_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Fetch a conversation thread and return it as an HTML partial."""

    try:
        session_id = request.session.get("session_id")
        uid = request.session.get("uid")
        if not session_id or not uid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.uid == conv_id) & (models.Conversation.user_uid == uid)
        )
    ).first()

    if not conversation or conversation.deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    bot_by_index = {msg["message_index"]: msg for msg in conversation.bot_messages}

    message_pairs = []
    for user_msg in sorted(
        conversation.user_messages, key=lambda m: m["message_index"]
    ):
        idx = user_msg["message_index"]
        raw_bot = bot_by_index.get(idx)
        if raw_bot is None:
            continue
        bot_msg = dict(raw_bot)
        if isinstance(bot_msg.get("sources"), str):
            bot_msg["sources"] = json.loads(bot_msg["sources"])
        if isinstance(bot_msg.get("tools_called"), str):
            bot_msg["tools_called"] = json.loads(bot_msg["tools_called"])
        message_pairs.append({"user_msg": user_msg, "bot_msg": bot_msg})

    return templates.TemplateResponse(
        "partials/conversation_thread.html",
        {
            "request": request,
            "message_pairs": message_pairs,
            "conv_id": str(conv_id),
        },
    )


# ---------------------------------------------------------------------------
# GET /conversations/s/{conv_share_id}  — public shared conversation page
# ---------------------------------------------------------------------------
@router.get("/s/{conv_share_id}")
async def fetch_shared_conversation(
    conv_share_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Render a read-only shared conversation as a full HTML page."""

    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.shared_link == conv_share_id)
            & (models.Conversation.shared)
        )
    ).first()

    if not conversation or conversation.deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    bot_by_index = {msg["message_index"]: msg for msg in conversation.bot_messages}

    message_pairs = []
    for user_msg in sorted(
        conversation.user_messages, key=lambda m: m["message_index"]
    ):
        idx = user_msg["message_index"]
        raw_bot = bot_by_index.get(idx)
        if raw_bot is None:
            continue
        bot_msg = dict(raw_bot)
        if isinstance(bot_msg.get("sources"), str):
            bot_msg["sources"] = json.loads(bot_msg["sources"])
        if isinstance(bot_msg.get("tools_called"), str):
            bot_msg["tools_called"] = json.loads(bot_msg["tools_called"])
        message_pairs.append({"user_msg": user_msg, "bot_msg": bot_msg})

    return templates.TemplateResponse(
        "shared.html",
        {
            "request": request,
            "message_pairs": message_pairs,
            "conv_id": conv_share_id,
            "title": conversation.title or "Shared Conversation",
        },
    )


# ---------------------------------------------------------------------------
# GET /conversations/list
# ---------------------------------------------------------------------------
@router.get("/list")
async def list_conversations(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the sidebar conversation list as an HTML partial."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user_conversations = db.scalars(
        select(models.Conversation)
        .where(models.Conversation.user_uid == uid)
        .where(not_(models.Conversation.deleted))
        .order_by(models.Conversation.updated_at.desc())
    ).all()

    convs = [
        {
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
        for conv in user_conversations
    ]

    return templates.TemplateResponse(
        "partials/sidebar_list.html",
        {"request": request, "conversations": convs},
    )
