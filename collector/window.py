"""Окно скана сегмента: дни недели (0 = понедельник) и интервал, в т.ч. через полночь.

Чистые функции без Django; время — локальное (Europe/Moscow, см. настройку TIME_ZONE).
"""

from __future__ import annotations

from datetime import datetime, time


def parse_window(scan_window: dict) -> tuple[set[int], time, time]:
    """Валидирует и разбирает jsonb-окно: {"days": [0..6], "start": "HH:MM", "end": "HH:MM"}."""
    days_raw = scan_window.get("days")
    if not isinstance(days_raw, list) or not days_raw:
        raise ValueError("окно скана: не заданы дни недели")
    days = set()
    for day in days_raw:
        if not isinstance(day, int) or not 0 <= day <= 6:
            raise ValueError(f"окно скана: неверный день недели {day!r}")
        days.add(day)
    try:
        start = time.fromisoformat(scan_window["start"])
        end = time.fromisoformat(scan_window["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("окно скана: время в формате HH:MM") from exc
    if start == end:
        raise ValueError("окно скана: начало и конец совпадают")
    return days, start, end


def in_scan_window(scan_window: dict, now: datetime) -> bool:
    """Разрешён ли скан в момент now.

    Окно через полночь относится к своему дню: ночь на вторник — понедельник.
    """
    days, start, end = parse_window(scan_window)
    today = now.weekday()
    current = now.time()

    if start < end:
        return today in days and start <= current < end
    # через полночь: [start, 24:00) — в день окна, [00:00, end) — в следующий день
    if current >= start:
        return today in days
    if current < end:
        return ((today - 1) % 7) in days
    return False
