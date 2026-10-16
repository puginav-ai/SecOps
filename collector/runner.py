"""Запуск внешних процессов скана. Единственная «грязная» точка — подменяется в тестах."""

from __future__ import annotations

import subprocess


class ScanError(RuntimeError):
    """nmap не смог отработать (не найден, таймаут, ненулевой код возврата)."""


def run_nmap(args: list[str], timeout: int = 600) -> str:
    """nmap → XML (stdout). Аргументы собираются в collector.nmap."""
    try:
        result = subprocess.run(  # noqa: S603 — аргументы строим сами, shell не используется
            [*args, "-oX", "-"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError(f"nmap не запустился: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()[:300]
        raise ScanError(f"nmap завершился с кодом {result.returncode}: {stderr}")
    return result.stdout
