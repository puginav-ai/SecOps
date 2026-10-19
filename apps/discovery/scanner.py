"""Сбор наблюдений сегмента: ICMP-sweep, порт-скан по профилю и пассивный сбор с роутеров.

Внешние вызовы — collector.runner.run_nmap и collector.mikrotik.fetch_router_data
(оба подменяются в тестах).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from django.conf import settings

from apps.registry.models import Segment
from collector.mikrotik import arp_hosts, fetch_router_data, merge_observations
from collector.nmap import (
    ObservedHost,
    build_service_args,
    build_sweep_args,
    chunk_cidr,
    parse_nmap_xml,
)
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


def collect_observations(segment: Segment) -> list[ObservedHost]:
    """Живые узлы сегмента; профиль top100 дополняет их портами/именем/ОС."""
    alive: list[ObservedHost] = []
    for chunk in chunk_cidr(segment.cidr):
        alive.extend(parse_nmap_xml(run_nmap(build_sweep_args(chunk))))

    if (
        segment.scan_profile
        in (
            Segment.ScanProfile.TOP100,
            Segment.ScanProfile.TOP100_SERVICES,
        )
        and alive
    ):
        detailed = {
            host.ip: host
            for host in parse_nmap_xml(
                run_nmap(
                    build_service_args(
                        [host.ip for host in alive],
                        version=segment.scan_profile == Segment.ScanProfile.TOP100_SERVICES,
                    )
                )
            )
        }
        # узел, «потерянный» при детальном скане, остаётся живым из свипа
        alive = [detailed.get(host.ip, host) for host in alive]

    passive, leases = passive_hosts(segment)
    if passive:
        alive = merge_observations(alive, passive, leases)
    return alive
