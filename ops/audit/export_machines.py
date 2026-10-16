"""Выгрузка списка машин: DHCP-аренды + ARP-таблицы роутеров → ops/audit/machines.txt.

Колонки TSV: ip, hostname, mac, источник (dhcp|arp|dhcp+arp), контур (кампус|КПЦ).
Запуск: make audit-list. Секретов не печатает.
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

KPC_ROUTER = "192.168.110.2"
KPC_USER = "specops-collector"
ZERO_MAC = "00:00:00:00:00:00"


def _connect(host: str, user: str) -> librouteros.api.Api:  # type: ignore[name-defined]
    return librouteros.connect(host, user, settings.MIKROTIK_API_PASSWORD, port=8728, timeout=10)


def _valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return False
    return True


def _valid_mac(mac: str) -> bool:
    return bool(mac) and mac.lower() != ZERO_MAC


def main() -> None:
    rows: dict[str, dict[str, str]] = {}

    api = _connect(settings.MIKROTIK_HOST, settings.MIKROTIK_API_USER)
    try:
        for lease in api.path("ip", "dhcp-server", "lease"):
            lease = dict(lease)
            ip = str(lease.get("address", ""))
            if lease.get("status") != "bound" or not _valid_ip(ip):
                continue
            row = rows.setdefault(ip, {"host": "", "mac": "", "src": "", "site": "кампус"})
            row["host"] = str(lease.get("host-name", "")).strip().strip("-")
            row["src"] = "dhcp"
        for arp in api.path("ip", "arp"):
            arp = dict(arp)
            ip, mac = str(arp.get("address", "")), str(arp.get("mac-address") or "")
            if not _valid_ip(ip) or not _valid_mac(mac):
                continue
            row = rows.setdefault(ip, {"host": "", "mac": "", "src": "", "site": "кампус"})
            row["mac"] = mac.lower()
            row["src"] = "dhcp+arp" if row["src"] == "dhcp" else (row["src"] or "arp")
    finally:
        api.close()

    try:
        kpc = _connect(KPC_ROUTER, KPC_USER)
        try:
            for arp in kpc.path("ip", "arp"):
                arp = dict(arp)
                ip, mac = str(arp.get("address", "")), str(arp.get("mac-address") or "")
                if not _valid_ip(ip) or not _valid_mac(mac) or ip in rows:
                    continue
                rows[ip] = {"host": "", "mac": mac.lower(), "src": "arp", "site": "КПЦ"}
        finally:
            kpc.close()
    except Exception as exc:  # роутер КПЦ может быть недоступен — список всё равно собирается
        print(f"КПЦ недоступен ({type(exc).__name__}): {str(exc)[:80]} — собираю только кампус")

    ordered = sorted(rows.items(), key=lambda item: ipaddress.ip_address(item[0]))
    out = Path(__file__).with_name("machines.txt")
    lines = [
        "\t".join([ip, row["host"], row["mac"], row["src"], row["site"]]) for ip, row in ordered
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    by_src: dict[str, int] = {}
    for _, row in ordered:
        by_src[row["src"]] = by_src.get(row["src"], 0) + 1
    stats = ", ".join(f"{key}={value}" for key, value in sorted(by_src.items()))
    print(f"machines.txt: {len(ordered)} адресов → {out}")
    print(f"источники: {stats}")


if __name__ == "__main__":
    main()
