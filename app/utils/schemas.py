import uuid
from datetime import datetime
from typing import Annotated, Optional, Literal, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from fastapi import Form

from ..cfg import settings

# ADD THIS in models FOR SQLALCHEMY ORM FALLBACK =>    model_config = ConfigDict(from_attributes=True)

class User_Create_Request(BaseModel):
    email: EmailStr
    username: str
    display_name: str
    password: str


class User_Login_Request(BaseModel):
    username: str
    password: str


class Conversation_Create_Request(BaseModel):
    query: str
    opt_web: bool = True
    model:   str  = f"{settings.llm_model_id}"

class Conversation_Continue_Request(BaseModel):
    query: str
    conversation_id: str
    opt_web: bool = True
    model: str = f"{settings.llm_model_id}"

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
