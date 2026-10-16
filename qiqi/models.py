"""Pydantic-схемы запросов/ответов."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------- groups ----------

class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    comment: str = ""


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    comment: str | None = None


# ---------- prompts ----------

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
    seed_mode: Literal["random", "fixed"] = "random"
    seed: int | None = None


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
    seed_mode: Literal["random", "fixed"] | None = None
    seed: int | None = None


# ---------- settings ----------

class SettingsPatch(BaseModel):
    theme: Literal["dark", "light"] | None = None
    last_group_id: int | None = None


# ---------- jobs ----------

class OrderIn(BaseModel):
    kind: Literal["preview", "fullsize"]
    count: int | None = Field(default=None, ge=1, le=64)
    parent_file_id: int | None = None
    size_name: str | None = None


class JobResultIn(BaseModel):
    file_id: int
    status: Literal["done", "error"]
    path: str | None = None
    meta_path: str | None = None
    seed: int | None = None
    steps: int | None = None
    cfg: float | None = None
    error: str | None = None

# ---------- files ----------

class FilePatch(BaseModel):
    rating: int | None = Field(default=None, ge=0, le=12)
    favorite: bool | None = None

