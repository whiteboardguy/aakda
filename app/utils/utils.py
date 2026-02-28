from colorama import init as colorama_init
from fastapi import Depends, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .print_utils import printStat
from . import models


colorama_init()

pwd_context = PasswordHash.recommended()


def hash(password: str):
    """returns a argon2 hashed string of the input string"""
    return pwd_context.hash(password)


def verifyPwd(plaintext_pwd, hashed_pwd):
    return pwd_context.verify(plaintext_pwd, hashed_pwd)


def get_session_user(request: Request, db):
    """Extract user from session, return User object or None"""
    email = request.session.get("email")
    if not email:
        return None
    user = db.scalars(select(models.User).where(models.User.email == email)).first()
    return user
