from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreatePostRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text cannot be empty or whitespace-only")
        return stripped


class PostResponse(BaseModel):
    id: int
    author_id: int
    text: str
    created_at: datetime
    author: Optional[UserResponse] = None


class PostListItem(BaseModel):
    id: int
    author_id: int
    text: str
    created_at: datetime
    author: UserResponse


class PostListResponse(BaseModel):
    posts: list[PostListItem]
    next_cursor: Optional[int] = None