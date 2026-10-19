"""Выгрузка списка машин: DHCP-аренды + ARP-таблицы роутеров → ops/audit/machines.txt.

Источники: основной роутер (кампус) + все дополнительные из `MIKROTIK_EXTRA_ROUTERS`.
Колонки TSV: ip, hostname, mac, источник (dhcp|arp|dhcp+arp), контур.
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

ZERO_MAC = "00:00:00:00:00:00"


def _connect(host: str, user: str) -> librouteros.api.Api:  # type: ignore[name-defined]
    return librouteros.connect(
        host, user, settings.MIKROTIK_API_PASSWORD, port=8728, timeout=10, encoding="UTF-8"
    )


def _valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return False
    return True


def _valid_mac(mac: str) -> bool:
    return bool(mac) and mac.lower() != ZERO_MAC


def _sources() -> list[tuple[str, str, str]]:
    """(host, user, метка контура): основной роутер + дополнительные из настроек."""
    sources = [(settings.MIKROTIK_HOST, settings.MIKROTIK_API_USER, "кампус")]
    for router in settings.MIKROTIK_EXTRA_ROUTERS:
        sources.append(
            (
                str(router.get("host", "")),
                str(router.get("user", "admin")),
                str(router.get("name") or router.get("host", "")),
            )
        )
    return sources


def main() -> None:
    rows: dict[str, dict[str, str]] = {}

    # DHCP-аренды основного роутера — источник имён
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
    finally:
        api.close()

    # ARP всех роутеров
    for host, user, label in _sources():
        if not host:
            continue
        try:
            router = _connect(host, user)
        except Exception as exc:
            print(f"{label} ({host}) недоступен: {type(exc).__name__}")
            continue
        try:
            for arp in router.path("ip", "arp"):
                arp = dict(arp)
                ip, mac = str(arp.get("address", "")), str(arp.get("mac-address") or "")
                if not _valid_ip(ip) or not _valid_mac(mac):
                    continue
                row = rows.setdefault(ip, {"host": "", "mac": "", "src": "", "site": label})
                row["mac"] = mac.lower()
                row["src"] = "dhcp+arp" if row["src"] == "dhcp" else (row["src"] or "arp")
        finally:
            router.close()

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
