"""Выгрузка списка АРМ из DHCP-аренд роутера → ops/audit/machines.txt.

Запуск: make audit-list (Docker, prod-настройки). Секретов не печатает.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # корень репозитория
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()

import librouteros  # noqa: E402
from django.conf import settings  # noqa: E402


def main() -> None:
    api = librouteros.connect(
        settings.MIKROTIK_HOST,
        settings.MIKROTIK_API_USER,
        settings.MIKROTIK_API_PASSWORD,
        port=8728,
    )
    try:
        leases = [dict(row) for row in api.path("ip", "dhcp-server", "lease")]
    finally:
        api.close()

    rows: list[tuple[str, str]] = []
    for lease in leases:
        if lease.get("status") != "bound" or not lease.get("address"):
            continue
        host = str(lease.get("host-name", "")).strip() or "-"
        rows.append((str(lease["address"]), host))
    rows.sort(key=lambda row: ipaddress.ip_address(row[0]))

    out = Path(__file__).with_name("machines.txt")
    out.write_text("\n".join(f"{ip}\t{host}" for ip, host in rows) + "\n", encoding="utf-8")
    print(f"machines.txt: {len(rows)} адресов → {out}")


if __name__ == "__main__":
    main()
