from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .print_utils import printStat


def make_session_token(user_uid: str, db):

    pre_existing_session = db.scalars(
        select(models.Session).where(models.Session.user_uid == user_uid)
    ).first()
    if pre_existing_session:
        db.delete(pre_existing_session)
        db.flush()

    new_user_session = models.Session(user_uid=user_uid)

    db.add(new_user_session)
    db.commit()
    db.refresh(new_user_session)

    return new_user_session.session_id


def revoke_user_session(user_uid: str, db):

    pre_existing_session = db.scalars(
        select(models.Session).where(models.Session.user_uid == user_uid)
    ).first()
    if pre_existing_session:
        try:
            db.delete(pre_existing_session)
            db.commit()
        except Exception as e:
            printStat("c", f"Session revocation failed for uid={user_uid}: {e}")


def session_is_valid(user_uid, input_session_id, db):

    target_session = db.scalars(
        select(models.Session).where(models.Session.user_uid == user_uid)
    ).first()

    if not target_session:
        return False

    # Check token expiry.
    now = datetime.now(timezone.utc)
    if target_session.expire_at is not None and target_session.expire_at < now:
        try:
            db.delete(target_session)
            db.commit()
        except Exception as e:
            printStat("w", f"Failed to delete expired session for uid={user_uid}: {e}")
        return False

    if input_session_id == str(target_session.session_id):
        return True

    return False
