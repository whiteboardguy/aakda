import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import not_, select
from sqlalchemy.orm import Session, attributes

from . import conv_opts
from ..utils import status as task_status, models, schemas
from ..utils.database import engine, get_db
from ..utils.print_utils import printStat
from ..utils.sandbox.sandbox import fetch_graph
from ..utils.sessions import session_is_valid
from ..utils.templating import templates

router = APIRouter(prefix="/conversations")
router.include_router(conv_opts.router)


# ---------------------------------------------------------------------------
# Background job: runs fetch_graph off the event loop, persists result,
# updates in-memory status dict so the poll endpoint can serve progress.
# ---------------------------------------------------------------------------
async def _run_job(
    conv_uid: str,
    user_uid: str,
    query: str,
    opt_web: bool,
    model: str,
    message_index: int,
    snapshot_user_messages: list,
    snapshot_bot_messages: list,
) -> None:

    loop = asyncio.get_running_loop()

    def on_status(msg: str) -> None:
        loop.call_soon_threadsafe(task_status.set_status, conv_uid, message_index, msg)

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

        # Persist with an independent DB session,
        # checking that the conversation belongs to the user.
        with Session(engine) as db:
            conversation = db.scalars(
                select(models.Conversation).where(
                    (models.Conversation.uid == conv_uid)
                    & (models.Conversation.user_uid == user_uid)
                    & not_(models.Conversation.deleted)
                )
            ).first()

            if not conversation:
                raise RuntimeError("Conversation not found")

            conversation.bot_messages.append(result)
            attributes.flag_modified(conversation, "bot_messages")
            conversation.updated_at = datetime.now(timezone.utc)
            db.commit()

    except Exception as exc:
        printStat(
            "c", f"Background job conv={conv_uid} idx={message_index} failed: {exc}"
        )
        task_status.set_error(conv_uid, message_index, str(exc))

    finally:
        # Only clear the status entry — errors are cleared by the poll endpoint
        # after it has delivered the error_bubble to the client.
        task_status._status.pop(f"{conv_uid}:{message_index}", None)


# ---------------------------------------------------------------------------
# POST /conversations/new
# ---------------------------------------------------------------------------
@router.post("/new")
async def create_conversation(
    request: Request,
    user_input: Annotated[schemas.Conversation_Create_Request, Form()],
    db: Session = Depends(get_db),
):
    """Create a new conversation, spawn background AI job, return polling loader."""

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
    task_status.set_status(conv_uid, 1, "Working…")

    asyncio.create_task(
        _run_job(
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
        "partials/loading_state.html",
        {
            "request": request,
            "conv_id": conv_uid,
            "message_index": 1,
            "query": user_input.query,
            "status_text": "Working…",
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
    """Continue an existing conversation; spawn background AI job, return polling loader."""

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
    task_status.set_status(conv_uid, new_message_index, "Working…")

    asyncio.create_task(
        _run_job(
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
        "partials/loading_state.html",
        {
            "request": request,
            "conv_id": conv_uid,
            "message_index": new_message_index,
            "query": user_input.query,
            "status_text": "Working…",
        },
    )


# ---------------------------------------------------------------------------
# GET /conversations/poll/{conv_id}/{message_index}
# ---------------------------------------------------------------------------
@router.get("/poll/{conv_id}/{message_index}")
async def poll_message(
    conv_id: UUID,
    message_index: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Poll endpoint: returns loading_state (not done), message_group (done), or error_bubble."""

    session_id = request.session.get("session_id")
    uid = request.session.get("uid")
    if not session_id or not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not session_is_valid(uid, session_id, db):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    conv_uid = str(conv_id)

    # Check for error first.
    error = task_status.get_error(conv_uid, message_index)
    if error is not None:
        task_status.clear(conv_uid, message_index)
        error_html = templates.env.get_template("partials/error_bubble.html").render(
            {"error_message": error}
        )
        return HTMLResponse(
            error_html,
            headers={
                "HX-Retarget": f"#poll-{conv_uid}-{message_index}",
                "HX-Reswap": "outerHTML",
            },
        )

    # Check if the bot message has been persisted.
    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.uid == conv_id)
            & (models.Conversation.user_uid == uid)
            & not_(models.Conversation.deleted)
        )
    ).first()

    if conversation:
        bot_by_index = {msg["message_index"]: msg for msg in conversation.bot_messages}
        raw_bot = bot_by_index.get(message_index)
        if raw_bot is not None:
            # Done — render the completed message group.
            bot_msg = dict(raw_bot)
            if isinstance(bot_msg.get("sources"), str):
                bot_msg["sources"] = json.loads(bot_msg["sources"])
            if isinstance(bot_msg.get("tools_called"), str):
                bot_msg["tools_called"] = json.loads(bot_msg["tools_called"])

            user_by_index = {
                msg["message_index"]: msg for msg in conversation.user_messages
            }
            user_msg = user_by_index.get(
                message_index, {"message": "", "message_index": message_index}
            )

            return templates.TemplateResponse(
                "partials/message_group.html",
                {
                    "request": request,
                    "user_msg": user_msg,
                    "bot_msg": bot_msg,
                    "conv_id": conv_uid,
                },
                headers={
                    "HX-Retarget": f"#poll-{conv_uid}-{message_index}",
                    "HX-Reswap": "outerHTML",
                },
            )

    # Still in progress — return just the updated status text.
    current_status = task_status.get_status(conv_uid, message_index)
    return HTMLResponse(current_status)


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
# GET /conversations/s/{conv_share_id}  — publicly shared conversation page
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
