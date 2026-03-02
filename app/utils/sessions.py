from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .utils import models

from .database import get_db



def make_session_token(user_uid: str, db):
    
    pre_existing_session = db.scalars(select(models.Session).where(models.Session.user_uid == user_uid)).first()
    if pre_existing_session:
        db.delete(pre_existing_session)

    new_user_session = models.Session(user_uid=user_uid)

    db.add(new_user_session)
    db.commit()
    db.refresh(new_user_session)

    return new_user_session.session_id



def revoke_user_session(user_uid: str, db):

    pre_existing_session = db.scalars(select(models.Session).where(models.Session.user_uid == user_uid)).first()
    if pre_existing_session:
        try:
            db.delete(pre_existing_session)
            db.commit()
        except:
            pass



def session_is_valid(user_uid, input_session_id, db):

    target_session = db.scalars(select(models.Session).where(models.Session.user_uid == user_uid)).first()

    if not target_session:
        return False

    if input_session_id == str(target_session.session_id):
        return True

    return False
