"""Загрузка qiqi.yaml и настройки приложения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "db_path": "prompts.sqlite",
    "paths": {
        "previews_dir": "previews",
        "fullsize_dir": "fullsize",
        "incoming_dir": "incoming",
        "deleted_dir": "deleted",
        "exports_dir": "exports",
    },
    "server": {"host": "127.0.0.1", "port": 8765},
    "qwen": {
        "default_cfg": 2.5,
        "cfg_green": [2.0, 3.0],
        "cfg_orange": [1.5, 4.0],
        "preview": {
            "count": 3,
            "steps": 20,
            "size": [768, 768],
        },
        "fullsize": {
            "steps": 40,
            "size": [1280, 1280],
        },
    },
}

CONFIG_NAME = "qiqi.yaml"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class QwenSizeConfig:
    steps: int = 20
    size: tuple[int, int] = (768, 768)


@dataclass
class QwenConfig:
    default_cfg: float = 2.5
    cfg_green: tuple[float, float] = (2.0, 3.0)
    cfg_orange: tuple[float, float] = (1.5, 4.0)
    preview: QwenSizeConfig = field(
        default_factory=lambda: QwenSizeConfig(steps=20, size=(768, 768))
    )
    fullsize: QwenSizeConfig = field(
        default_factory=lambda: QwenSizeConfig(steps=40, size=(1280, 1280))
    )


@dataclass
class PathsConfig:
    previews_dir: Path = Path("previews")
    fullsize_dir: Path = Path("fullsize")
    incoming_dir: Path = Path("incoming")
    deleted_dir: Path = Path("deleted")
    exports_dir: Path = Path("exports")


@dataclass
class Settings:
    base_dir: Path
    db_path: Path
    paths: PathsConfig
    server: ServerConfig = field(default_factory=ServerConfig)
    qwen: QwenConfig = field(default_factory=QwenConfig)

    # удобные алиасы (используются в api.py, app.js через /api/meta)
    @property
    def previews_dir(self) -> Path:
        return self.paths.previews_dir

    @property
    def fullsize_dir(self) -> Path:
        return self.paths.fullsize_dir

    @property
    def incoming_dir(self) -> Path:
        return self.paths.incoming_dir

    @property
    def deleted_dir(self) -> Path:
        return self.paths.deleted_dir

    @property
    def exports_dir(self) -> Path:
        return self.paths.exports_dir


def _merge(defaults: dict, user: dict) -> dict:
    out = dict(defaults)
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def find_config(start: Path | None = None) -> Path | None:
    cwd = (start or Path.cwd()) / CONFIG_NAME
    if cwd.is_file():
        return cwd
    here = Path(__file__).resolve().parent.parent / CONFIG_NAME
    if here.is_file():
        return here
    return None


def ensure_config(path: Path) -> Path:
    if not path.exists():
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f, allow_unicode=True, sort_keys=False)
    return path


def _resolve(base: Path, raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        config_path = find_config()
    if config_path is None:
        config_path = Path.cwd() / CONFIG_NAME
        ensure_config(config_path)

    with config_path.open("r", encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}

    cfg = _merge(DEFAULT_CONFIG, user_cfg)

    base_dir = config_path.resolve().parent

    db_path = _resolve(base_dir, cfg["db_path"])

    paths_raw = cfg.get("paths") or {}
    paths = PathsConfig(
        previews_dir=_resolve(base_dir, paths_raw.get("previews_dir", "previews")),
        fullsize_dir=_resolve(base_dir, paths_raw.get("fullsize_dir", "fullsize")),
        incoming_dir=_resolve(base_dir, paths_raw.get("incoming_dir", "incoming")),
        deleted_dir=_resolve(base_dir, paths_raw.get("deleted_dir", "deleted")),
        exports_dir=_resolve(base_dir, paths_raw.get("exports_dir", "exports")),
    )

    srv_raw = cfg.get("server") or {}
    qwen_raw = cfg.get("qwen") or {}
    prev_raw = qwen_raw.get("preview") or {}
    full_raw = qwen_raw.get("fullsize") or {}

    def _size(raw, default):
        v = raw if raw else default
        return (int(v[0]), int(v[1]))

    settings = Settings(
        base_dir=base_dir,
        db_path=db_path,
        paths=paths,
        server=ServerConfig(
            host=str(srv_raw.get("host", "127.0.0.1")),
            port=int(srv_raw.get("port", 8765)),
        ),
        qwen=QwenConfig(
            default_cfg=float(qwen_raw.get("default_cfg", 2.5)),
            cfg_green=tuple(qwen_raw.get("cfg_green", [2.0, 3.0])),
            cfg_orange=tuple(qwen_raw.get("cfg_orange", [1.5, 4.0])),
            preview=QwenSizeConfig(
                steps=int(prev_raw.get("steps", 20)),
                size=_size(prev_raw.get("size"), (768, 768)),
            ),
            fullsize=QwenSizeConfig(
                steps=int(full_raw.get("steps", 40)),
                size=_size(full_raw.get("size"), (1280, 1280)),
            ),
        ),
    )

    # создаём все рабочие папки
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for d in (paths.previews_dir, paths.fullsize_dir, paths.incoming_dir,
              paths.deleted_dir, paths.exports_dir):
        d.mkdir(parents=True, exist_ok=True)

    return settings


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings()
    return _SETTINGS


def reset_settings_cache() -> None:
    global _SETTINGS
    _SETTINGS = None


# на случай запуска из другого места
os.environ.setdefault("QIQI_CONFIG", str(Path.cwd() / CONFIG_NAME))
