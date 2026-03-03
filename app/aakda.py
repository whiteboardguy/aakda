import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import not_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .cfg import settings
from .limiter import limiter
from .routes import auth, conversations, users
from .utils import models
from .utils.database import get_db
from .utils.print_utils import printStat
from .utils.purge import run_purge_loop, run_session_purge_loop
from .utils.sessions import session_is_valid
from .utils.templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.opts_workers > 1:
        printStat(
            "w",
            "OPTIONS_WORKERS > 1: in-memory task status is not shared across workers. Poll results may be incorrect.",
        )
    purge_task = asyncio.create_task(run_purge_loop())
    session_purge_task = asyncio.create_task(run_session_purge_loop())
    yield
    purge_task.cancel()
    session_purge_task.cancel()
    for task in (purge_task, session_purge_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.security_session_secret,
    session_cookie="cookies",
    same_site="lax",
    path="/",
)  # ty: ignore[invalid-argument-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.aakda_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.plot.ly; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(users.router)


# 404 and 500 pages
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    if request.headers.get("HX-Request"):
        return HTMLResponse("", status_code=404)
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse("500.html", {"request": request}, status_code=500)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Auth helper for page render routes
# ---------------------------------------------------------------------------
def _is_authenticated(request: Request, db: Session) -> bool:
    try:
        session_id = request.session.get("session_id")
        uid = request.session.get("uid")
        if not session_id or not uid:
            return False
        return session_is_valid(uid, session_id, db)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Page render routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root(request: Request, db: Session = Depends(get_db)):
    if not _is_authenticated(request, db):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        "chat.html", {"request": request, "initial_conv_id": None}
    )


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/500")
async def error_page(request: Request):
    return templates.TemplateResponse("500.html", {"request": request}, status_code=500)


@app.get("/c/{conv_id}")
async def chat_page_conv(
    conv_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """Serve the chat shell pre-loaded with a specific conversation."""
    if not _is_authenticated(request, db):
        return RedirectResponse("/login", status_code=302)

    uid = request.session.get("uid")
    conversation = db.scalars(
        select(models.Conversation).where(
            (models.Conversation.uid == conv_id)
            & (models.Conversation.user_uid == uid)
            & not_(models.Conversation.deleted)
        )
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "initial_conv_id": str(conv_id)},
    )
