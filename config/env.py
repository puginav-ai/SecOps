"""Мини-загрузчик .env (без внешних зависимостей) и чтение переменных окружения.

Приоритет: реальное окружение > .env > default. Секреты живут только в окружении/.env.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Читает .env (KEY=VALUE, '#' — комментарий), не перетирая существующее окружение."""
    path = path or BASE_DIR / ".env"
    if not path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        parsed[key] = value
        os.environ.setdefault(key, value)
    return parsed


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Не задана обязательная переменная окружения: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    return int(env(name, str(default)))


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def env_json(name: str, default: list | dict):
    """JSON-значение из окружения (например, список роутеров). Пусто → default."""
    import json

    raw = env(name, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name}: ожидается JSON ({exc})") from exc
