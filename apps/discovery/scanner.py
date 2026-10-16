"""Сбор наблюдений сегмента: ICMP-sweep, порт-скан по профилю и пассивный сбор с Mikrotik.

Внешние вызовы — collector.runner.run_nmap и collector.mikrotik.fetch_router_data
(оба подменяются в тестах).
"""

from __future__ import annotations

import logging

from django.conf import settings

from apps.registry.models import Segment
from collector.mikrotik import RouterData, arp_hosts, fetch_router_data, merge_observations
from collector.nmap import (
    ObservedHost,
    build_service_args,
    build_sweep_args,
    chunk_cidr,
    parse_nmap_xml,
)
from collector.runner import run_nmap

logger = logging.getLogger(__name__)


def passive_hosts(segment: Segment) -> tuple[list[ObservedHost], RouterData | None]:
    """Узлы из ARP роутера в подсети сегмента. Роутер не настроен/недоступен → пусто."""
    if not settings.MIKROTIK_HOST:
        return [], None
    try:
        data = fetch_router_data(
            settings.MIKROTIK_HOST,
            settings.MIKROTIK_API_USER,
            settings.MIKROTIK_API_PASSWORD,
            use_ssl=settings.MIKROTIK_API_SSL,
        )
    except Exception:  # сетевой сбой не должен валить скан: сегмент сканируется как раньше
        logger.exception(
            "mikrotik api unavailable", extra={"segment_id": segment.pk, "cidr": segment.cidr}
        )
        return [], None
    return arp_hosts(data.arp, segment.cidr), data


def collect_observations(segment: Segment) -> list[ObservedHost]:
    """Живые узлы сегмента; профиль top100 дополняет их портами/именем/ОС."""
    alive: list[ObservedHost] = []
    for chunk in chunk_cidr(segment.cidr):
        alive.extend(parse_nmap_xml(run_nmap(build_sweep_args(chunk))))

    if segment.scan_profile == Segment.ScanProfile.TOP100 and alive:
        detailed = {
            host.ip: host
            for host in parse_nmap_xml(run_nmap(build_service_args([host.ip for host in alive])))
        }
        # узел, «потерянный» при детальном скане, остаётся живым из свипа
        alive = [detailed.get(host.ip, host) for host in alive]

    passive, data = passive_hosts(segment)
    if passive:
        alive = merge_observations(alive, passive, data.leases if data else ())
    return alive
