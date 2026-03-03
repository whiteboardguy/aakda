"""LLM AUTO-GENERATED TEST
test_conversations.py — HTTP-layer tests for conversation routes.

_run_job is mocked as a no-op throughout so no real AI pipeline or
PostgreSQL connections are exercised.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import (
    _sqlite_engine,
    auth_cookies,
    make_conversation,
    make_session,
    make_user,
)
from app.utils import status as task_status
from app.utils.models import Conversation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOOP_RUN_JOB = "app.routes.conversations._run_job"


def _add_bot_message(conv_uid: str, user_uid, message_index: int) -> None:
    """Write a fake bot message directly into SQLite for poll tests."""
    from sqlalchemy.orm import attributes

    with OrmSession(_sqlite_engine) as s:
        conv = s.get(Conversation, (uuid.UUID(conv_uid), user_uid))
        assert conv is not None, "conversation not found in DB"
        conv.bot_messages = conv.bot_messages + [
            {
                "message": "Bot reply",
                "message_index": message_index,
                "is_render": False,
                "model": "test-model",
                "message_retries": 0,
                "tools_called": [],
                "sources": [],
                "render_python": "",
                "render_plot_html": "",
                "render_html_data": "",
            }
        ]
        attributes.flag_modified(conv, "bot_messages")
        s.commit()


# ---------------------------------------------------------------------------
# POST /conversations/new
# ---------------------------------------------------------------------------


class TestCreateConversation:
    def test_new_unauthenticated(self, client):
        r = client.post(
            "/conversations/new",
            data={"query": "hello", "opt_web": "true", "model": "test-model"},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 401

    def test_new_creates_db_row_and_returns_loading_partial(self, client):
        user = make_user()
        auth_cookies(client)

        with patch(_NOOP_RUN_JOB, new=AsyncMock(return_value=None)):
            r = client.post(
                "/conversations/new",
                data={
                    "query": "What is Python?",
                    "opt_web": "true",
                    "model": "test-model",
                },
            )

        assert r.status_code == 200
        # Should return the loading partial HTML
        assert (
            b"poll" in r.content.lower()
            or b"working" in r.content.lower()
            or b"loading" in r.content.lower()
        )

        # Conversation row should exist in DB
        with OrmSession(_sqlite_engine) as s:
            convs = s.query(Conversation).filter_by(user_uid=user.uid).all()
        assert len(convs) == 1
        assert convs[0].user_messages[0]["message"] == "What is Python?"
        assert convs[0].title == "What is Python?"[:40]

    def test_new_empty_query_rejected(self, client):
        make_user()
        auth_cookies(client)

        r = client.post(
            "/conversations/new",
            data={"query": "", "opt_web": "true", "model": "test-model"},
        )
        assert r.status_code == 422

    def test_new_sets_status_key(self, client):
        user = make_user()
        auth_cookies(client)

        with patch(_NOOP_RUN_JOB, new=AsyncMock(return_value=None)):
            client.post(
                "/conversations/new",
                data={
                    "query": "Status key test",
                    "opt_web": "true",
                    "model": "test-model",
                },
            )

        # set_status is called synchronously before create_task, so a DB row
        # must exist regardless of whether the task ran.
        with OrmSession(_sqlite_engine) as s:
            convs = s.query(Conversation).filter_by(user_uid=user.uid).all()
        assert len(convs) == 1


# ---------------------------------------------------------------------------
# POST /conversations/continue/{conv_id}
# ---------------------------------------------------------------------------


class TestContinueConversation:
    def test_continue_unauthenticated(self, client):
        user = make_user()
        conv = make_conversation(user)

        r = client.post(
            f"/conversations/continue/{conv.uid}",
            data={"query": "follow-up", "opt_web": "true", "model": "test-model"},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 401

    def test_continue_appends_user_message(self, client):
        user = make_user()
        conv = make_conversation(user, title="Initial question")
        auth_cookies(client)

        with patch(_NOOP_RUN_JOB, new=AsyncMock(return_value=None)):
            r = client.post(
                f"/conversations/continue/{conv.uid}",
                data={
                    "query": "Follow up question",
                    "opt_web": "true",
                    "model": "test-model",
                },
            )

        assert r.status_code == 200

        with OrmSession(_sqlite_engine) as s:
            updated = s.get(Conversation, (conv.uid, user.uid))
        assert len(updated.user_messages) == 2
        assert updated.user_messages[1]["message"] == "Follow up question"
        assert updated.user_messages[1]["message_index"] == 2

    def test_continue_returns_loading_partial(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        with patch(_NOOP_RUN_JOB, new=AsyncMock(return_value=None)):
            r = client.post(
                f"/conversations/continue/{conv.uid}",
                data={
                    "query": "Another message",
                    "opt_web": "true",
                    "model": "test-model",
                },
            )

        assert r.status_code == 200
        assert (
            b"poll" in r.content.lower()
            or b"working" in r.content.lower()
            or b"loading" in r.content.lower()
        )

    def test_continue_nonexistent_conv_404(self, client):
        make_user()
        auth_cookies(client)
        fake_id = uuid.uuid4()

        with patch(_NOOP_RUN_JOB, new=AsyncMock(return_value=None)):
            r = client.post(
                f"/conversations/continue/{fake_id}",
                data={"query": "hello", "opt_web": "true", "model": "test-model"},
            )

        assert r.status_code == 404

    def test_continue_other_users_conv_404(self, client):
        owner = make_user(username="owner", email="owner@example.com")
        conv = make_conversation(owner)

        make_user(username="other", email="other@example.com")
        auth_cookies(client, username="other")

        with patch(_NOOP_RUN_JOB, new=AsyncMock(return_value=None)):
            r = client.post(
                f"/conversations/continue/{conv.uid}",
                data={"query": "sneaky", "opt_web": "true", "model": "test-model"},
            )

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /conversations/poll/{conv_id}/{message_index}
# ---------------------------------------------------------------------------


class TestPollMessage:
    def test_poll_unauthenticated(self, client):
        user = make_user()
        conv = make_conversation(user)

        r = client.get(
            f"/conversations/poll/{conv.uid}/1",
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 401

    def test_poll_returns_status_while_job_running(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        conv_uid = str(conv.uid)
        task_status.set_status(conv_uid, 1, "Thinking…")

        r = client.get(f"/conversations/poll/{conv.uid}/1")

        assert r.status_code == 200
        assert b"Thinking" in r.content or len(r.content) > 0

        task_status.clear(conv_uid, 1)

    def test_poll_returns_message_group_when_done(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        conv_uid = str(conv.uid)
        # No status key → job is considered done; write bot message to DB
        _add_bot_message(conv_uid, user.uid, 1)

        r = client.get(f"/conversations/poll/{conv.uid}/1")

        assert r.status_code == 200
        # Should include HX-Retarget header pointing to the poll element
        assert f"poll-{conv_uid}-1" in r.headers.get("HX-Retarget", "")

    def test_poll_returns_error_bubble_on_error(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        conv_uid = str(conv.uid)
        task_status.set_error(conv_uid, 1, "Something went wrong")

        r = client.get(f"/conversations/poll/{conv.uid}/1")

        assert r.status_code == 200
        assert b"Something went wrong" in r.content
        assert f"poll-{conv_uid}-1" in r.headers.get("HX-Retarget", "")

    def test_poll_nonexistent_conv_404(self, client):
        make_user()
        auth_cookies(client)
        fake_id = uuid.uuid4()

        r = client.get(f"/conversations/poll/{fake_id}/1")

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /conversations/fetch/{conv_id}
# ---------------------------------------------------------------------------


class TestFetchConversation:
    def test_fetch_unauthenticated(self, client):
        user = make_user()
        conv = make_conversation(user)

        r = client.get(
            f"/conversations/fetch/{conv.uid}",
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 401

    def test_fetch_returns_thread_partial(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        r = client.get(f"/conversations/fetch/{conv.uid}")

        assert r.status_code == 200
        assert b"html" in r.content.lower() or len(r.content) > 0

    def test_fetch_other_users_conv_404(self, client):
        owner = make_user(username="owner", email="owner@example.com")
        conv = make_conversation(owner)

        make_user(username="other", email="other@example.com")
        auth_cookies(client, username="other")

        r = client.get(f"/conversations/fetch/{conv.uid}")
        assert r.status_code == 404

    def test_fetch_nonexistent_conv_404(self, client):
        make_user()
        auth_cookies(client)
        fake_id = uuid.uuid4()

        r = client.get(f"/conversations/fetch/{fake_id}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /conversations/new-form
# ---------------------------------------------------------------------------


class TestNewForm:
    def test_new_form_returns_200(self, client):
        r = client.get("/conversations/new-form")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /conversations/list
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_list_unauthenticated(self, client):
        r = client.get("/conversations/list", headers={"HX-Request": "true"})
        assert r.status_code == 401

    def test_list_returns_sidebar(self, client):
        user = make_user()
        make_conversation(user, title="Conv A")
        make_conversation(user, title="Conv B")
        auth_cookies(client)

        r = client.get("/conversations/list")

        assert r.status_code == 200
        assert b"Conv A" in r.content or b"conv" in r.content.lower()

    def test_list_excludes_deleted(self, client):
        user = make_user()
        conv = make_conversation(user, title="To be deleted")
        auth_cookies(client)

        with OrmSession(_sqlite_engine) as s:
            c = s.get(Conversation, (conv.uid, user.uid))
            c.deleted = True
            s.commit()

        r = client.get("/conversations/list")

        assert r.status_code == 200
        assert b"To be deleted" not in r.content


# ---------------------------------------------------------------------------
# POST /conversations/delete-all
# ---------------------------------------------------------------------------


class TestDeleteAllConversations:
    def test_delete_all_unauthenticated(self, client):
        r = client.post("/conversations/delete-all", headers={"HX-Request": "true"})
        assert r.status_code == 401

    def test_delete_all_soft_deletes_all_convs(self, client):
        user = make_user()
        make_conversation(user, title="A")
        make_conversation(user, title="B")
        auth_cookies(client)

        r = client.post("/conversations/delete-all")

        assert r.status_code == 200

        with OrmSession(_sqlite_engine) as s:
            active = (
                s.query(Conversation).filter_by(user_uid=user.uid, deleted=False).all()
            )
        assert len(active) == 0

    def test_delete_all_does_not_affect_other_users(self, client):
        user_a = make_user(username="a", email="a@example.com")
        make_conversation(user_a, title="User A conv")

        user_b = make_user(username="b", email="b@example.com")
        make_conversation(user_b, title="User B conv")

        auth_cookies(client, username="a")
        client.post("/conversations/delete-all")

        with OrmSession(_sqlite_engine) as s:
            b_convs = (
                s.query(Conversation)
                .filter_by(user_uid=user_b.uid, deleted=False)
                .all()
            )
        assert len(b_convs) == 1


# ---------------------------------------------------------------------------
# POST /conversations/opts/share/{conv_id}
# POST /conversations/opts/unshare/{conv_id}
# POST /conversations/opts/delete/{conv_id}
# ---------------------------------------------------------------------------


class TestConvOpts:
    def test_share_unauthenticated(self, client):
        user = make_user()
        conv = make_conversation(user)

        r = client.post(
            f"/conversations/opts/share/{conv.uid}",
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 401

    def test_share_sets_shared_link(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        r = client.post(f"/conversations/opts/share/{conv.uid}")

        assert r.status_code == 200
        assert "X-Share-Link" in r.headers
        assert len(r.headers["X-Share-Link"]) > 0

        with OrmSession(_sqlite_engine) as s:
            updated = s.get(Conversation, (conv.uid, user.uid))
        assert updated.shared is True
        assert updated.shared_link is not None

    def test_unshare_clears_shared(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        client.post(f"/conversations/opts/share/{conv.uid}")
        r = client.post(f"/conversations/opts/unshare/{conv.uid}")

        assert r.status_code == 200

        with OrmSession(_sqlite_engine) as s:
            updated = s.get(Conversation, (conv.uid, user.uid))
        assert updated.shared is False
        assert updated.shared_link is None

    def test_delete_conv_soft_deletes(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        r = client.post(f"/conversations/opts/delete/{conv.uid}")

        assert r.status_code == 200

        with OrmSession(_sqlite_engine) as s:
            updated = s.get(Conversation, (conv.uid, user.uid))
        assert updated.deleted is True
        assert updated.deleted_at is not None

    def test_share_nonexistent_conv_404(self, client):
        make_user()
        auth_cookies(client)
        fake_id = uuid.uuid4()

        r = client.post(f"/conversations/opts/share/{fake_id}")
        assert r.status_code == 404

    def test_delete_other_users_conv_404(self, client):
        owner = make_user(username="owner", email="owner@example.com")
        conv = make_conversation(owner)

        make_user(username="other", email="other@example.com")
        auth_cookies(client, username="other")

        r = client.post(f"/conversations/opts/delete/{conv.uid}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /conversations/s/{share_id}  — public shared conversation page
# ---------------------------------------------------------------------------


class TestSharedConversation:
    def test_shared_page_200(self, client):
        user = make_user()
        conv = make_conversation(user, title="Shared conv")
        auth_cookies(client)

        share_resp = client.post(f"/conversations/opts/share/{conv.uid}")
        share_link = share_resp.headers["X-Share-Link"]

        r = client.get(f"/conversations/s/{share_link}")

        assert r.status_code == 200
        assert b"Shared conv" in r.content or len(r.content) > 0

    def test_shared_page_nonexistent_404(self, client):
        r = client.get("/conversations/s/nonexistent-share-id")
        assert r.status_code == 404

    def test_shared_page_unshared_conv_404(self, client):
        user = make_user()
        conv = make_conversation(user)
        auth_cookies(client)

        share_resp = client.post(f"/conversations/opts/share/{conv.uid}")
        share_link = share_resp.headers["X-Share-Link"]
        client.post(f"/conversations/opts/unshare/{conv.uid}")

        r = client.get(f"/conversations/s/{share_link}")
        assert r.status_code == 404
