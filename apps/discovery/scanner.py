"""Сбор наблюдений сегмента: ICMP-sweep, порт-скан по профилю и пассивный сбор с роутеров.

Внешние вызовы — collector.runner.run_nmap и collector.mikrotik.fetch_router_data
(оба подменяются в тестах).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace

from django.conf import settings

from apps.registry.models import Segment
from collector.mikrotik import arp_hosts, fetch_router_data, merge_observations
from collector.nmap import (
    ObservedHost,
    build_service_args,
    build_sweep_args,
    build_version_args,
    chunk_cidr,
    parse_nmap_xml,
    version_ports,
)
from collector.osfingerprint import build_os_probe_args, parse_os_probe_xml
from collector.runner import run_nmap

logger = logging.getLogger(__name__)


def router_sources() -> list[tuple[str, str, str, bool]]:
    """Настроенные источники пассивных данных: основной роутер + дополнительные (JSON-список)."""
    sources = [
        (
            settings.MIKROTIK_HOST,
            settings.MIKROTIK_API_USER,
            settings.MIKROTIK_API_PASSWORD,
            settings.MIKROTIK_API_SSL,
        )
    ]
    for router in settings.MIKROTIK_EXTRA_ROUTERS:
        sources.append(
            (
                str(router.get("host", "")),
                str(router.get("user", "admin")),
                str(router.get("password", "")),
                False,
            )
        )
    return sources


def passive_hosts(segment: Segment) -> tuple[list[ObservedHost], list[Mapping[str, str]]]:
    """ARP-наблюдения всех настроенных роутеров в подсети сегмента + DHCP-аренды для имён.

    Недоступный роутер скан не валит: пишется лог, источник пропускается.
    """
    hosts: list[ObservedHost] = []
    leases: list[Mapping[str, str]] = []
    for host, user, password, use_ssl in router_sources():
        if not host:
            continue
        try:
            data = fetch_router_data(host, user, password, use_ssl=use_ssl)
        except Exception:
            logger.exception(
                "mikrotik api unavailable",
                extra={"segment_id": segment.pk, "cidr": segment.cidr, "host": host},
            )
            continue
        hosts.extend(arp_hosts(data.arp, segment.cidr))
        leases.extend(data.leases)
    return hosts, leases


def collect_observations(segment: Segment, profile: str | None = None) -> list[ObservedHost]:
    """Живые узлы сегмента; profile — разовый профиль вместо сохранённого в сегменте.

    Ручной скан («Просканировать сейчас») передаёт глубокий профиль: его цель — наполнить
    паспорта портами и версиями, даже если ежедневный обход сегмента только ping-sweep.
    """
    profile = profile or segment.scan_profile
    alive: list[ObservedHost] = []
    for chunk in chunk_cidr(segment.cidr):
        alive.extend(parse_nmap_xml(run_nmap(build_sweep_args(chunk))))

    if (
        profile
        in (
            Segment.ScanProfile.TOP100,
            Segment.ScanProfile.TOP100_SERVICES,
        )
        and alive
    ):
        detailed = {
            host.ip: host
            for host in parse_nmap_xml(run_nmap(build_service_args([host.ip for host in alive])))
        }
        # узел, «потерянный» при детальном скане, остаётся живым из свипа
        alive = [detailed.get(host.ip, host) for host in alive]

        # Версия Windows без учётных данных: SMB/RDP-скрипты на уже открытых портах
        os_targets = [host.ip for host in alive if set(host.ports) & {445, 3389}]
        if os_targets:
            detected = parse_os_probe_xml(run_nmap(build_os_probe_args(os_targets)))
            alive = [
                replace(
                    host,
                    os_name=detected.get(host.ip, {}).get("os") or host.os_name,
                    hostname=host.hostname or detected.get(host.ip, {}).get("hostname", ""),
                )
                for host in alive
            ]

    if profile == Segment.ScanProfile.TOP100_SERVICES and alive:
        alive = _with_service_versions(alive)

    passive, leases = passive_hosts(segment)
    if passive:
        alive = merge_observations(alive, passive, leases)
    return alive


# Версии — батчами: в одном запуске nmap часть хостов пропускает по host-timeout
VERSION_BATCH_SIZE = 16


def _with_service_versions(hosts: list[ObservedHost]) -> list[ObservedHost]:
    """Вторая ступень профиля с версиями: -sV по объединению открытых портов, батчами.

    Хосты без открытых портов не трогаем: у них и версий не будет. Батчи ограничивают
    host-timeout на весь запуск: на 100+ хостах nmap иначе пропускает часть хостов
    («Skipping host due to host timeout»), и версии теряются.
    """
    ported = {host.ip: host.ports for host in hosts if host.ports}
    if not ported:
        return hosts
    ordered_ips = sorted(ported)
    versioned: dict[str, ObservedHost] = {}
    for start in range(0, len(ordered_ips), VERSION_BATCH_SIZE):
        batch = ordered_ips[start : start + VERSION_BATCH_SIZE]
        ports = version_ports({port for ip in batch for port in ported[ip]})
        if not ports:
            # В батче только принтеры/raw-порты: версии не запрашиваем, чтобы не печатать.
            continue
        for host in parse_nmap_xml(run_nmap(build_version_args(batch, ports))):
            versioned[host.ip] = host
    return [
        replace(host, services=versioned[host.ip].services)
        if versioned.get(host.ip, None) and versioned[host.ip].services
        else host
        for host in hosts
    ]
