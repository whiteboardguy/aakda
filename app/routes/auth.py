from ..utils.print_utils import printStat
from starlette.status import (
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_200_OK,
    HTTP_401_UNAUTHORIZED,
    HTTP_409_CONFLICT,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi import APIRouter, Form, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response

from ..cfg import settings
from ..utils import schemas, models
from ..utils.database import get_db
from ..utils.utils import hash, verifyPwd
from ..utils.sessions import make_session_token, revoke_user_session

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/users/signup")
async def create_user(
    request: Request,
    user_input: Annotated[schemas.User_Create_Request, Form()],
    db: Session = Depends(get_db),
):

    if db.scalars(
        select(models.User).where(models.User.username == user_input.username)
    ).first():
        raise HTTPException(
            status_code=HTTP_409_CONFLICT, detail="Username provided already exists."
        )
    if db.scalars(
        select(models.User).where(models.User.email == user_input.email)
    ).first():
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Email address provided already in use.",
        )

    new_user = models.User(**user_input.model_dump())

    unhashed = new_user.password

    try:
        new_user.password = hash(unhashed)
    except Exception as e:
        printStat("c", "Password hashing system has failed.")
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)

    if new_user.password == unhashed:
        printStat("c", "Password hashing system has failed.")
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)

    del unhashed

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return Response(status_code=200)


@router.post("/users/login")
async def login_user(
    request: Request,
    input: Annotated[schemas.User_Login_Request, Form()],
    db: Session = Depends(get_db),
):

    tg_user = db.scalars(
        select(models.User).where(models.User.username == input.username)
    ).first()

    if not tg_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials"
        )

    if verifyPwd(input.password, tg_user.password):
        request.session["email"] = str(tg_user.email)
        request.session["uid"] = str(tg_user.uid)
        request.session["session_id"] = str(make_session_token(tg_user.uid, db))

        return Response(status_code=200)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials"
    )


@router.post("/users/logout")
async def logout_user(request: Request, db: Session = Depends(get_db)):
    try:
        uid = request.session.get("uid")
        if uid:
            revoke_user_session(uid, db)
    except Exception as e:
        printStat("w", f"Session revocation error during logout: {e}")
    finally:
        request.session.clear()

    return Response(status_code=200)
