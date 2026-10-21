"""Парсинг nmap XML и сборка аргументов скана в рамках бюджета (SDD §5.2).

Только чистые функции: сетевые вызовы — в collector/runner.py.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from xml.etree import ElementTree as ET

# Бюджет скана — SDD §5.2
HOST_TIMEOUT = "40s"  # с учётом глобального max-rate: на 100+ хостах 10 с не хватало и nmap
#                       пропускал хосты целиком («Skipping host due to host timeout»)
VERSION_PORTS_TIMEOUT = "90s"  # вторая ступень (-sV) — по узкому набору открытых портов
MAX_RATE = "300"  # pps: глобальный лимит на весь запуск, а не на хост
TOP_PORTS = "100"
CHUNK_PREFIX = 24

# Порты, на которые нельзя отправлять payload при -sV:
# 515 — nmap LPDString-проба (\x01default\n) печатается Canon как задание;
# 9100-9107 — raw/PJL (nmap сам исключает их, но фиксируем явно);
# 631 — IPP/HTTP-пробы, чтобы не тревожить печать.
VERSION_UNSAFE_PORTS = frozenset({515, 631, *range(9100, 9108)})
PRINTER_SCAN_EXCLUDE = "515,631,9100-9107"


def version_ports(ports: Iterable[int]) -> list[int]:
    """Порты, безопасные для определения версий: без LPD/raw-печати/IPP."""
    return sorted({int(port) for port in ports if int(port) not in VERSION_UNSAFE_PORTS})


@dataclass(frozen=True)
class ObservedHost:
    """Узел, увиденный коллектором. mac — нормализованный (нижний регистр, ':')."""

    ip: str
    mac: str | None = None
    hostname: str = ""
    os_name: str = ""
    ports: tuple[int, ...] = ()
    services: tuple[dict, ...] = ()  # [{"port", "service", "product", "version", "extrainfo"}]
    source: str = "nmap"


def parse_nmap_xml(xml_text: str) -> list[ObservedHost]:
    """XML nmap → список живых хостов. Битые порты/адреса пропускаются, хосты без IPv4 — тоже."""
    # XML приходит от нашего же subprocess (nmap -oX), не из сети — S314 неактуален.
    root = ET.fromstring(xml_text)  # noqa: S314
    hosts: list[ObservedHost] = []
    for host in root.findall("host"):
        status = host.find("status")
        if status is not None and status.get("state") != "up":
            continue

        ip, mac = "", None
        for address in host.findall("address"):
            addrtype = address.get("addrtype")
            if addrtype == "ipv4":
                ip = address.get("addr", "")
            elif addrtype == "mac" and address.get("addr"):
                mac = address.get("addr", "").lower()
        if not ip:
            continue
        try:  # доверяем только валидным адресам
            ipaddress.ip_address(ip)
        except ValueError:
            continue

        hostname_el = host.find("hostnames/hostname")
        hostname = hostname_el.get("name", "") if hostname_el is not None else ""
        os_el = host.find("os/osmatch")
        os_name = os_el.get("name", "") if os_el is not None else ""

        ports: list[int] = []
        services: list[dict] = []
        for port in host.findall("ports/port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            try:
                portid = int(port.get("portid", ""))
            except ValueError:
                continue
            ports.append(portid)
            service_el = port.find("service")
            if service_el is None:
                continue
            service = {
                "port": portid,
                "service": service_el.get("name", ""),
                "product": service_el.get("product", ""),
                "version": service_el.get("version", ""),
                "extrainfo": service_el.get("extrainfo", ""),
            }
            if service["service"] or service["product"] or service["version"]:
                services.append(service)

        hosts.append(
            ObservedHost(
                ip=ip,
                mac=mac,
                hostname=hostname,
                os_name=os_name,
                ports=tuple(sorted(ports)),
                services=tuple(services),
            )
        )
    return hosts


def chunk_cidr(cidr: str, prefix: int = CHUNK_PREFIX) -> list[str]:
    """Делит подсеть на куски не крупнее /prefix. Подсеть мельче — как есть."""
    network = ipaddress.ip_network(cidr, strict=False)
    if network.prefixlen >= prefix:
        return [str(network)]
    return [str(subnet) for subnet in network.subnets(new_prefix=prefix)]


def build_sweep_args(target: str) -> list[str]:
    """ICMP/ping-sweep — аккуратно, без DNS: `-n` (в контуре DNS может отсутствовать),
    умеренный темп T3. T2 здесь не годится: на /24 это минуты."""
    return ["nmap", "-sn", "-n", "-T3", target]


def build_service_args(targets: list[str]) -> list[str]:
    """top-100 портов для живых узлов: бюджет host-timeout/max-rate (SDD §5.2), без DNS.

    T3, а не T2: у T2 минимальная задержка 0.4 с на пробу, и top-100 не укладывается
    в host-timeout (проверено). --max-rate — ГЛОБАЛЬНЫЙ лимит: при 100 pps на сегменте
    из ~120 хостов каждый не успевал и nmap пропускал хосты целиком, поэтому 300 pps
    и host-timeout 40 с (проверено на живом сегменте: 19 из 19 хостов с портами).
    """
    return [
        "nmap",
        "-n",
        "-T3",
        "--top-ports",
        TOP_PORTS,
        "--host-timeout",
        HOST_TIMEOUT,
        "--max-rate",
        MAX_RATE,
        "--exclude-ports",
        PRINTER_SCAN_EXCLUDE,
        *targets,
    ]


def build_version_args(targets: list[str], ports: list[int]) -> list[str]:
    """Определение версий служб — вторая ступень профиля «top-100 + версии».

    Только по уже найденным безопасным открытым портам: -sV по всем 100 портам не
    укладывается в host-timeout на хостах с «filtered» портами, и nmap пропускал их
    целиком («Skipping host due to host timeout» — проверено на живом сегменте).
    Печатные порты отфильтровываются: LPD-проба nmap печатается на МФУ как мусор.
    """
    safe_ports = version_ports(ports)
    if not safe_ports:
        raise ValueError("no safe ports for version scan")
    return [
        "nmap",
        "-n",
        "-T3",
        "-sV",
        "--version-light",
        "--script",
        "banner,http-title",
        "-p",
        ",".join(str(port) for port in safe_ports),
        "--host-timeout",
        VERSION_PORTS_TIMEOUT,
        "--max-rate",
        MAX_RATE,
        *targets,
    ]
