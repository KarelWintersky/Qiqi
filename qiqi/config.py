"""Загрузка qiqi.yaml и настройки приложения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG = {
    "db_path": "prompts.sqlite",
    "previews_dir": "previews",
    "exports_dir": "exports",
    "server": {"host": "127.0.0.1", "port": 8765},
    "qwen": {
        "default_cfg": 2.5,
        "cfg_green": [2.0, 3.0],
        "cfg_orange": [1.5, 4.0],
    },
}

CONFIG_NAME = "qiqi.yaml"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class QwenConfig:
    default_cfg: float = 2.5
    cfg_green: tuple[float, float] = (2.0, 3.0)
    cfg_orange: tuple[float, float] = (1.5, 4.0)


@dataclass
class Settings:
    base_dir: Path
    db_path: Path
    previews_dir: Path
    exports_dir: Path
    server: ServerConfig = field(default_factory=ServerConfig)
    qwen: QwenConfig = field(default_factory=QwenConfig)


def _merge(defaults: dict, user: dict) -> dict:
    out = dict(defaults)
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def find_config(start: Path | None = None) -> Path | None:
    """Ищет qiqi.yaml в CWD, затем рядом со скриптом."""
    cwd = (start or Path.cwd()) / CONFIG_NAME
    if cwd.is_file():
        return cwd
    here = Path(__file__).resolve().parent.parent / CONFIG_NAME
    if here.is_file():
        return here
    return None


def ensure_config(path: Path) -> Path:
    """Создаёт qiqi.yaml с дефолтами, если файла нет."""
    if not path.exists():
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f, allow_unicode=True, sort_keys=False)
    return path


def load_settings(config_path: Path | None = None) -> Settings:
    if config_path is None:
        config_path = find_config()
    if config_path is None:
        config_path = Path.cwd() / CONFIG_NAME
        ensure_config(config_path)

    with config_path.open("r", encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}

    cfg: dict[str, Any] = _merge(DEFAULT_CONFIG, user_cfg)

    base_dir = config_path.resolve().parent

    db_path = (base_dir / cfg["db_path"]).resolve()
    previews_dir = (base_dir / cfg["previews_dir"]).resolve()
    exports_dir = (base_dir / cfg["exports_dir"]).resolve()

    srv_raw = cfg.get("server") or {}
    qwen_raw = cfg.get("qwen") or {}

    settings = Settings(
        base_dir=base_dir,
        db_path=db_path,
        previews_dir=previews_dir,
        exports_dir=exports_dir,
        server=ServerConfig(
            host=str(srv_raw.get("host", "127.0.0.1")),
            port=int(srv_raw.get("port", 8765)),
        ),
        qwen=QwenConfig(
            default_cfg=float(qwen_raw.get("default_cfg", 2.5)),
            cfg_green=tuple(qwen_raw.get("cfg_green", [2.0, 3.0])),
            cfg_orange=tuple(qwen_raw.get("cfg_orange", [1.5, 4.0])),
        ),
    )

    settings.previews_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    return settings


def get_settings() -> Settings:
    """Кэширует настройки, чтобы FastAPI не читал файл на каждый запрос."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings()
    return _SETTINGS


_SETTINGS: Settings | None = None


def reset_settings_cache() -> None:
    global _SETTINGS
    _SETTINGS = None


# на случай, если кто-то захочет запускать из другого места
os.environ.setdefault("QIQI_CONFIG", str(Path.cwd() / CONFIG_NAME))

