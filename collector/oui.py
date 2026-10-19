"""Вендор по MAC из OUI-таблицы IEEE (оффлайн: файл в репозитории, сеть на объекте не нужна).

Таблица `collector/data/oui.csv` — публичный реестр IEEE (MA-L, 24-битные префиксы).
Обновление — вручную раз в год: скачать с https://standards-oui.ieee.org/oui/oui.csv.
"""

from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

OUI_CSV = Path(__file__).resolve().parent / "data" / "oui.csv"
HEXDIGITS = frozenset("0123456789abcdefABCDEF")


def normalize_mac(mac: str) -> str:
    """MAC → 12 hex-символов в верхнем регистре без разделителей; "" — не MAC."""
    digits = "".join(char for char in (mac or "") if char in HEXDIGITS)
    return digits.upper() if len(digits) == 12 else ""


@lru_cache(maxsize=1)
def _oui_table() -> dict[str, str]:
    table: dict[str, str] = {}
    try:
        with OUI_CSV.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                prefix = (row.get("Assignment") or "").strip().upper()
                vendor = (row.get("Organization Name") or "").strip()
                if len(prefix) == 6 and vendor:
                    table[prefix] = vendor
    except OSError:
        logger.warning("OUI-таблица недоступна: %s", OUI_CSV)
    return table


def vendor_for_mac(mac: str) -> str:
    """Вендор по первым 24 битам MAC; "" — если MAC или префикс неизвестен."""
    normalized = normalize_mac(mac)
    if not normalized:
        return ""
    return _oui_table().get(normalized[:6], "")
