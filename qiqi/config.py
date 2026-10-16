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
            "steps": 20,
            "count": 3,
            "sizes": {
                "square": [320, 320],
                "wide":   [1472, 1104],
                "tall":   [1104, 1472],
            },
            "default_size": "square",
        },
        "fullsize": {
            "steps": 40,
            "sizes": {
                "square": [1280, 1280],
                "wide":   [1472, 1104],
                "tall":   [1104, 1472],
            },
            "default_size": "square",
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
    count: int = 1                      # для fullsize не используется
    sizes: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {"square": (768, 768)}
    )
    default_size: str = "square"

    def resolve_size(self, name: str | None = None) -> tuple[int, int]:
        key = name or self.default_size
        if key not in self.sizes:
            raise KeyError(f"unknown size name: {key}")
        return self.sizes[key]

    def size_names(self) -> list[str]:
        return list(self.sizes.keys())


@dataclass
class QwenConfig:
    default_cfg: float = 2.5
    cfg_green: tuple[float, float] = (2.0, 3.0)
    cfg_orange: tuple[float, float] = (1.5, 4.0)
    preview: QwenSizeConfig = field(
        default_factory=lambda: QwenSizeConfig(steps=20, count=3, sizes={"square": (320, 320)})
    )
    fullsize: QwenSizeConfig = field(
        default_factory=lambda: QwenSizeConfig(steps=40, sizes={"square": (1280, 1280)})
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


def _parse_sizes(raw: Any) -> dict[str, tuple[int, int]]:
    if not isinstance(raw, dict) or not raw:
        return {"square": (768, 768)}
    out: dict[str, tuple[int, int]] = {}
    for name, wh in raw.items():
        try:
            w, h = int(wh[0]), int(wh[1])
        except (TypeError, ValueError, IndexError):
            continue
        out[str(name)] = (w, h)
    if not out:
        out = {"square": (768, 768)}
    return out


def _parse_size_cfg(raw: dict, default_steps: int, default_count: int) -> QwenSizeConfig:
    sizes = _parse_sizes(raw.get("sizes"))
    default_size = str(raw.get("default_size") or next(iter(sizes)))
    if default_size not in sizes:
        default_size = next(iter(sizes))
    return QwenSizeConfig(
        steps=int(raw.get("steps", default_steps)),
        count=int(raw.get("count", default_count)),
        sizes=sizes,
        default_size=default_size,
    )


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
            preview=_parse_size_cfg(prev_raw, default_steps=20, default_count=3),
            fullsize=_parse_size_cfg(full_raw, default_steps=40, default_count=1),
        ),
    )

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


os.environ.setdefault("QIQI_CONFIG", str(Path.cwd() / CONFIG_NAME))
