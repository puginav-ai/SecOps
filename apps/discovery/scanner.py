"""Сбор наблюдений сегмента: ICMP-sweep и порт-скан по профилю (SDD §5.2).

Единственная точка внешних вызовов — collector.runner.run_nmap (подменяется в тестах).
"""

from __future__ import annotations

from apps.registry.models import Segment
from collector.nmap import (
    ObservedHost,
    build_service_args,
    build_sweep_args,
    chunk_cidr,
    parse_nmap_xml,
)
from collector.runner import run_nmap


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

    return alive
