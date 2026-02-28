from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from starlette.middleware.sessions import SessionMiddleware

from .cfg import settings

from .routes import test, auth, users, conversations

from .utils.database import get_db, engine

from .utils import models

db: Session = Depends(get_db)

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# cors_origins = [
#         "http://localhost",
#         "http://localhost:5555",
#         '*'
# ]
#
# app.add_middleware(
#         CORSMiddleware,
#         allow_origins=cors_origins,
#         allow_credentials=True,
#         allow_methods=['*'],
#         allow_headers=['*'],
# )

app.add_middleware(
        SessionMiddleware,
        secret_key=settings.security_session_secret,
        session_cookie="cookies",
        same_site="lax",
        path="/",
) # ty: ignore[invalid-argument-type]


# app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(test.router)
app.include_router(auth.router)
