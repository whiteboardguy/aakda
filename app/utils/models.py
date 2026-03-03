from sqlalchemy.ext.mutable import MutableDict, MutableList
from .database import Base
from ..cfg import settings
from .print_utils import printStat

import uuid
from typing import Optional, List

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.sqltypes import TIMESTAMP


class User(Base):
    __tablename__ = "users"

    # by the server, during creation
    uid = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    # by the user, during creation
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # by the server, post creation
    if settings.DEBUG is True:
        printStat("w", "New users are verified automatically (DEBUG mode).")
        verified = mapped_column(Boolean, default=True)
    elif settings.opts_autoverify is True:
        printStat(
            "o", "New users are verified automatically (Auto Verify rule is true)."
        )
        verified = mapped_column(Boolean, default=True)
    else:
        verified = mapped_column(Boolean, default=False)


class Conversation(Base):
    __tablename__ = "conversations"

    # server-made
    uid = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_uid = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.uid", ondelete="NO ACTION"),
        primary_key=True,
    )

    created_at = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    deleted = mapped_column(Boolean(), default=False, nullable=False)
    shared = mapped_column(Boolean(), default=False, nullable=False)

    user_messages: Mapped[List[dict]] = mapped_column(
        MutableList.as_mutable(JSON), default=lambda: []
    )
    bot_messages: Mapped[List[dict]] = mapped_column(
        MutableList.as_mutable(JSON), default=lambda: []
    )

    shared_link: Mapped[Optional[str]] = mapped_column(
        String(), default=None, nullable=True
    )

    deleted_at = mapped_column(TIMESTAMP(timezone=True), default=None, nullable=True)

    locked_state: Mapped[bool] = mapped_column(Boolean(), default=False)

    # user made
    title: Mapped[str] = mapped_column(String())


class Session(Base):
    __tablename__ = "sessions"

    session_id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_uid = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.uid", ondelete="CASCADE"),
        primary_key=True,
    )

    expire_at = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW() + INTERVAL '7 days'")
    )
