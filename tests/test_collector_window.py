"""Окно скана: обычное и через полночь, границы, ошибки формата (SDD §5.2).

2026-10-12 — понедельник, 2026-10-13 — вторник.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from collector.window import in_scan_window, parse_window

DAY_WINDOW = {"days": [0], "start": "09:00", "end": "18:00"}
NIGHT_WINDOW = {"days": [0], "start": "23:00", "end": "05:00"}


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 12, 9, 0), True),  # начало включительно
        (datetime(2026, 10, 12, 10, 0), True),
        (datetime(2026, 10, 12, 17, 59), True),
        (datetime(2026, 10, 12, 18, 0), False),  # конец исключительно
        (datetime(2026, 10, 12, 8, 59), False),
        (datetime(2026, 10, 13, 10, 0), False),  # вторник не в днях окна
    ],
)
def test_day_window(now, expected):
    assert in_scan_window(DAY_WINDOW, now) is expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 12, 23, 0), True),  # ночь понедельника начинается в 23:00
        (datetime(2026, 10, 12, 22, 59), False),
        (datetime(2026, 10, 13, 2, 0), True),  # перетекает в следующий день
        (datetime(2026, 10, 13, 5, 0), False),  # конец исключительно
        (datetime(2026, 10, 13, 6, 0), False),
        (datetime(2026, 10, 11, 23, 30), False),  # воскресенье не в днях окна
    ],
)
def test_night_window_crosses_midnight(now, expected):
    assert in_scan_window(NIGHT_WINDOW, now) is expected


def test_multiple_days():
    window = {"days": [0, 1], "start": "09:00", "end": "18:00"}

    assert in_scan_window(window, datetime(2026, 10, 13, 10, 0)) is True
    assert in_scan_window(window, datetime(2026, 10, 12, 10, 0)) is True
    assert in_scan_window(window, datetime(2026, 10, 14, 10, 0)) is False


def test_bad_window_raises_value_error():
    with pytest.raises(ValueError):
        parse_window({"days": [], "start": "09:00", "end": "18:00"})
    with pytest.raises(ValueError):
        parse_window({"days": [7], "start": "09:00", "end": "18:00"})
    with pytest.raises(ValueError):
        parse_window({"days": [0], "start": "09:00", "end": "09:00"})
    with pytest.raises(ValueError):
        parse_window({"days": [0], "start": "ночью", "end": "05:00"})
    with pytest.raises(ValueError):
        parse_window({"days": [0], "start": "09:00"})
