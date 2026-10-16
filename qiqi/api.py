"""FastAPI-приложение Qiqi."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db as _db_module
from .config import get_settings
from .db import Database
from .models import (
    GroupIn, GroupPatch, PromptIn, PromptPatch,
    SettingsPatch, OrderIn, JobResultIn, FilePatch,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Qiqi", version="0.1.0")

_settings = get_settings()
_db_module.set_settings_getter(get_settings)

# Это нужно, потому что db.py не должен импортировать config.py напрямую (был бы цикл). Разрываем через сеттер.

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
    q = _settings.qwen
    return {
        "cfg_green": list(q.cfg_green),
        "cfg_orange": list(q.cfg_orange),
        "default_cfg": q.default_cfg,
        "preview": {
            "steps": q.preview.steps,
            "count": q.preview.count,
            "sizes": {k: list(v) for k, v in q.preview.sizes.items()},
            "default_size": q.preview.default_size,
        },
        "fullsize": {
            "steps": q.fullsize.steps,
            "sizes": {k: list(v) for k, v in q.fullsize.sizes.items()},
            "default_size": q.fullsize.default_size,
        },
        "db_path": str(_settings.db_path),
        "previews_dir": str(_settings.previews_dir),
        "fullsize_dir": str(_settings.fullsize_dir),
        "exports_dir": str(_settings.exports_dir),
    }

# ---------- jobs ----------

@app.get("/api/jobs")
def api_list_jobs(
    status: str | None = None,
    prompt_id: int | None = None,
    group_id: int | None = None,
    kind: str | None = None,
    limit: int = 100,
):
    return db.list_jobs(status=status, prompt_id=prompt_id,
                        group_id=group_id, kind=kind, limit=limit)


@app.get("/api/jobs/next")
def api_next_job():
    """Отдаёт самую старую pending-партию и переводит её в running."""
    job = db.claim_next_job()
    if not job:
        return Response(status_code=204, content=None)
    return job


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: int):
    job = db.get_job_with_files(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.post("/api/jobs/{job_id}/result")
def api_job_result(job_id: int, payload: JobResultIn):
    try:
        job = db.apply_job_result(
            job_id=job_id,
            file_id=payload.file_id,
            status=payload.status,
            path=payload.path,
            meta_path=payload.meta_path,
            seed=payload.seed,
            steps=payload.steps,
            cfg=payload.cfg,
            error=payload.error,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.post("/api/jobs/{job_id}/cancel", status_code=200)
def api_cancel_job(job_id: int):
    if not db.cancel_job(job_id):
        raise HTTPException(400, "job not cancellable")
    return db.get_job(job_id)


# ---------- orders ----------

@app.post("/api/prompts/{prompt_id}/order", status_code=201)
def api_order_for_prompt(prompt_id: int, payload: OrderIn):
    if not db.get_prompt(prompt_id):
        raise HTTPException(404, "prompt not found")

    try:
        if payload.kind == "preview":
            cfg_q = _settings.qwen.preview
            count = payload.count or cfg_q.count
            job = db.create_preview_job(prompt_id, count, payload.size_name)
            return job

        # fullsize
        if payload.parent_file_id is not None:
            parent = db.get_file(payload.parent_file_id)
        else:
            parent = db.best_preview_for_prompt(prompt_id)

        if not parent:
            raise HTTPException(400, "no ready preview to base fullsize on")
        if parent["prompt_id"] != prompt_id:
            raise HTTPException(400, "parent preview belongs to another prompt")

        return db.create_fullsize_job(parent["id"], payload.size_name)

    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/groups/{group_id}/order", status_code=201)
def api_order_for_group(group_id: int, payload: OrderIn):
    if payload.kind != "preview":
        raise HTTPException(400, "group order supports only preview")
    if not db.get_group(group_id):
        raise HTTPException(404, "group not found")

    cfg_q = _settings.qwen.preview
    count = payload.count or cfg_q.count
    try:
        jobs = db.create_preview_jobs_for_group(group_id, count, payload.size_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"created": len(jobs), "jobs": jobs}


@app.post("/api/files/{file_id}/fullsize", status_code=201)
def api_order_fullsize_for_file(file_id: int, payload: dict = Body(default={})):
    """Заказать fullsize по конкретному превью."""
    parent = db.get_file(file_id)
    if not parent:
        raise HTTPException(404, "file not found")
    if parent["kind"] != "preview":
        raise HTTPException(400, "only preview can have fullsize")
    size_name = payload.get("size_name") if isinstance(payload, dict) else None
    try:
        return db.create_fullsize_job(file_id, size_name)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- files ----------

@app.get("/api/prompts/{prompt_id}/files")
def api_prompt_files(prompt_id: int, include_deleted: bool = False):
    if not db.get_prompt(prompt_id):
        raise HTTPException(404, "prompt not found")
    return db.list_files(prompt_id=prompt_id, include_deleted=include_deleted)


@app.get("/api/files/{file_id}")
def api_get_file(file_id: int):
    f = db.get_file(file_id)
    if not f:
        raise HTTPException(404, "file not found")
    return f


@app.patch("/api/files/{file_id}")
def api_patch_file(file_id: int, payload: FilePatch):
    f = db.update_file(file_id, rating=payload.rating, favorite=payload.favorite)
    if not f:
        raise HTTPException(404, "file not found")
    return f


@app.delete("/api/files/{file_id}", status_code=204)
def api_delete_file(file_id: int):
    if not db.mark_file_deleted(file_id):
        raise HTTPException(404, "file not found")
    return Response(status_code=204)


@app.get("/api/files/{file_id}/raw")
def api_file_raw(file_id: int):
    f = db.get_file(file_id)
    if not f or not f["path"]:
        raise HTTPException(404, "file not available")
    base = _settings.previews_dir if f["kind"] == "preview" else _settings.fullsize_dir
    p = (base / f["path"]).resolve()
    if not p.is_file():
        raise HTTPException(404, "file missing on disk")
    media = "image/png"
    if p.suffix.lower() in (".jpg", ".jpeg"):
        media = "image/jpeg"
    elif p.suffix.lower() == ".webp":
        media = "image/webp"
    return FileResponse(p, media_type=media)


@app.get("/api/files/{file_id}/meta")
def api_file_meta(file_id: int):
    f = db.get_file(file_id)
    if not f or not f["meta_path"]:
        raise HTTPException(404, "meta not available")
    base = _settings.previews_dir if f["kind"] == "preview" else _settings.fullsize_dir
    p = (base / f["meta_path"]).resolve()
    if not p.is_file():
        raise HTTPException(404, "meta file missing on disk")
    return FileResponse(p, media_type="application/json")




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