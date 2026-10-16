"""FastAPI-приложение Qiqi."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import Database
from .models import GroupIn, GroupPatch, PromptIn, PromptPatch, SettingsPatch

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Qiqi", version="0.1.0")

_settings = get_settings()
db = Database(_settings.db_path)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)


# ---------- HTML ----------

@app.get("/")
def index():
    # Отдаём файл напрямую — без Jinja2, чтобы не ловить баги шаблонизатора.
    return FileResponse(BASE_DIR / "templates" / "index.html", media_type="text/html")


# ---------- meta ----------

@app.get("/api/meta")
def api_meta():
    return {
        "cfg_green": list(_settings.qwen.cfg_green),
        "cfg_orange": list(_settings.qwen.cfg_orange),
        "default_cfg": _settings.qwen.default_cfg,
        "db_path": str(_settings.db_path),
        "previews_dir": str(_settings.previews_dir),
        "exports_dir": str(_settings.exports_dir),
    }

# ---------- settings ----------

@app.get("/api/settings")
def api_get_settings():
    s = db.get_settings()
    # дефолты
    return {
        "theme": s.get("theme", "dark"),
        "last_group_id": int(s["last_group_id"]) if s.get("last_group_id") else None,
    }


@app.patch("/api/settings")
def api_patch_settings(payload: SettingsPatch):
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        db.set_setting(k, str(v))
    return api_get_settings()


# ---------- groups ----------

@app.get("/api/groups")
def api_list_groups():
    return db.list_groups()


@app.post("/api/groups", status_code=201)
def api_create_group(payload: GroupIn):
    try:
        return db.create_group(payload.name, payload.comment)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/groups/{group_id}")
def api_get_group(group_id: int):
    g = db.get_group(group_id)
    if not g:
        raise HTTPException(404, "group not found")
    return g


@app.patch("/api/groups/{group_id}")
def api_update_group(group_id: int, payload: GroupPatch):
    g = db.update_group(group_id, payload.name, payload.comment)
    if not g:
        raise HTTPException(404, "group not found")
    return g


@app.delete("/api/groups/{group_id}", status_code=204)
def api_delete_group(group_id: int):
    if not db.delete_group(group_id):
        raise HTTPException(404, "group not found")
    return Response(status_code=204, content=None)


# ---------- prompts ----------

@app.get("/api/prompts")
def api_list_prompts(
    group_id: int | None = None,
    favorites_only: bool = False,
    min_rating: int | None = None,
    search: str | None = None,
    sort: str = "favorite",
):
    return db.list_prompts(
        group_id=group_id,
        favorites_only=favorites_only,
        min_rating=min_rating,
        search=search,
        sort=sort,
    )

@app.post("/api/prompts", status_code=201)
def api_create_prompt(payload: PromptIn):
    if not db.get_group(payload.group_id):
        raise HTTPException(400, "group not found")
    return db.create_prompt(payload.model_dump())


@app.get("/api/prompts/{prompt_id}")
def api_get_prompt(prompt_id: int):
    p = db.get_prompt(prompt_id)
    if not p:
        raise HTTPException(404, "prompt not found")
    return p


@app.patch("/api/prompts/{prompt_id}")
def api_update_prompt(prompt_id: int, payload: PromptPatch):
    data = payload.model_dump(exclude_none=True)
    p = db.update_prompt(prompt_id, data)
    if not p:
        raise HTTPException(404, "prompt not found")
    return p


@app.delete("/api/prompts/{prompt_id}", status_code=204)
def api_delete_prompt(prompt_id: int):
    if not db.delete_prompt(prompt_id):
        raise HTTPException(404, "prompt not found")
    return Response(status_code=204, content=None)