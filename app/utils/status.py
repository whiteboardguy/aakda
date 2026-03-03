"""
status.py — lightweight in-memory status tracker for background AI tasks.

Key format: "{conv_id}:{message_index}"
"""

from typing import Optional

_status: dict[str, str] = {}
_errors: dict[str, str] = {}


def set_status(conv_id: str, message_index: int, text: str) -> None:
    _status[f"{conv_id}:{message_index}"] = text


def get_status(conv_id: str, message_index: int) -> str:
    return _status.get(f"{conv_id}:{message_index}", "Working…")


def set_error(conv_id: str, message_index: int, text: str) -> None:
    _errors[f"{conv_id}:{message_index}"] = text


def get_error(conv_id: str, message_index: int) -> Optional[str]:
    return _errors.get(f"{conv_id}:{message_index}")


def clear(conv_id: str, message_index: int) -> None:
    key = f"{conv_id}:{message_index}"
    _status.pop(key, None)
    _errors.pop(key, None)
