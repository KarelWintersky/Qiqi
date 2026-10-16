"""Точка входа: python -m qiqi или uv run qiqi."""
from __future__ import annotations

import argparse

import uvicorn

from .config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="qiqi", description="Qiqi prompt catalog")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    host = args.host or settings.server.host
    port = args.port or settings.server.port

    print("=" * 55)
    print(f"Qiqi запущен: http://{host}:{port}")
    print(f"БД:      {settings.db_path}")
    print(f"Превью:  {settings.previews_dir}")
    print(f"Экспорт: {settings.exports_dir}")
    print("Ctrl+C — остановить.")
    print("=" * 55)

    uvicorn.run(
        "qiqi.api:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()