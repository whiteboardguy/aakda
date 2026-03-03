from typing import List

from pydantic import BaseModel, EmailStr, Field, field_validator

from fastapi import Form

from ..cfg import settings


class User_Create_Request(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class User_Login_Request(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class Conversation_Request(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    opt_web: bool = True
    model: str = f"{settings.llm_model_id}"

    @field_validator("model", mode="before")
    @classmethod
    def _default_model(cls, v: str) -> str:
        return v.strip() or settings.llm_model_id


# Semantic meaning ig
Conversation_Create_Request = Conversation_Request
Conversation_Continue_Request = Conversation_Request


class U_msg(BaseModel):
    message: str
    message_index: int


class B_msg(BaseModel):
    is_render: bool
    message: str
    model: str
    message_retries: int
    tools_called: List
    sources: List[dict]
    render_python: str
    render_plot_html: str
    render_html_data: str
    message_index: int
