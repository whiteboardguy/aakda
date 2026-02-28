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
