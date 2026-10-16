"""Pydantic-схемы запросов/ответов."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    comment: str = ""


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    comment: str | None = None


class PromptIn(BaseModel):
    group_id: int
    title: str = ""
    positive: str = ""
    negative: str = ""
    no_negative: bool = False
    cfg: float = 2.5
    comment: str = ""
    rating: int = Field(default=0, ge=0, le=12)
    favorite: bool = False


class PromptPatch(BaseModel):
    group_id: int | None = None
    title: str | None = None
    positive: str | None = None
    negative: str | None = None
    no_negative: bool | None = None
    cfg: float | None = None
    comment: str | None = None
    rating: int | None = Field(default=None, ge=0, le=12)
    favorite: bool | None = None

class JobOrderIn(BaseModel):
    size: Literal["preview", "fullsize"]

class SettingsPatch(BaseModel):
    theme: Literal["dark", "light"] | None = None
    last_group_id: int | None = None

