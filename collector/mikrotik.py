"""Пассивное обнаружение через RouterOS API (Mikrotik): ARP-таблица и DHCP-аренды (SDD §5.2).

Только чтение (`/ip/arp`, `/ip/dhcp-server/lease`). Преобразование строк — чистые функции
(тестируются без сети); единственный сетевой вызов — fetch_router_data (подменяется в тестах).
"""

from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from collector.nmap import ObservedHost

ZERO_MAC = "00:00:00:00:00:00"


@dataclass(frozen=True)
class RouterData:
    """Выгрузка роутера: ARP, DHCP-аренды, имя, адреса, соседи и маршруты."""

    arp: tuple[Mapping[str, str], ...] = ()
    leases: tuple[Mapping[str, str], ...] = ()
    identity: str = ""
    addresses: tuple[Mapping[str, str], ...] = ()
    neighbors: tuple[Mapping[str, str], ...] = ()
    routes: tuple[Mapping[str, str], ...] = ()


def fetch_router_data(
    host: str,
    username: str,
    password: str,
    *,
    use_ssl: bool = False,
    timeout: float = 10.0,
) -> RouterData:
    """Читает ARP и DHCP-аренды через RouterOS API. Ошибки обрабатывает вызывающий."""
    import librouteros  # импорт ленивый: без Mikrotik приложение живёт и без библиотеки

    kwargs: dict = {"port": 8729 if use_ssl else 8728, "timeout": timeout}
    if use_ssl:
        # роутер в контуре — обычно с самоподписанным сертификатом: цепочку не проверяем
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs["ssl_wrapper"] = context

    api = librouteros.connect(host, username, password, **kwargs)
    try:
        arp = tuple(dict(row) for row in api.path("ip", "arp"))
        leases = tuple(
            dict(row)
            for row in api.path("ip", "dhcp-server", "lease")
            if row.get("status") == "bound"
        )
        identity_rows = tuple(dict(row) for row in api.path("system", "identity"))
        addresses = tuple(dict(row) for row in api.path("ip", "address"))
        neighbors = tuple(dict(row) for row in api.path("ip", "neighbor"))
        routes = tuple(dict(row) for row in api.path("ip", "route"))
    finally:
        api.close()
    identity = str(identity_rows[0].get("name", "")) if identity_rows else ""
    return RouterData(
        arp=arp,
        leases=leases,
        identity=identity,
        addresses=addresses,
        neighbors=neighbors,
        routes=routes,
    )


def normalized_neighbors(rows: Iterable[Mapping[str, str]]) -> list[dict]:
    """Строки /ip/neighbor → [{address, identity, interface, platform, mac}].

    Соседи (MNDP/LLDP/CDP) — источник связей роутер—роутер на карте сети (SDD §5.10):
    в строке соседа есть адрес, имя и локальный интерфейс, через который его видно.
    """
    result: list[dict] = []
    for row in rows:
        address = str(row.get("address", "")).strip()
        identity = str(row.get("identity", "")).strip()
        if not address and not identity:
            continue
        result.append(
            {
                "address": address,
                "identity": identity,
                "interface": str(row.get("interface", "")).strip(),
                "platform": str(row.get("platform", "")).strip(),
                "mac": str(row.get("mac-address", "")).strip().lower(),
            }
        )
    return result


def normalized_routes(rows: Iterable[Mapping[str, str]]) -> list[dict]:
    """Строки /ip/route → [{dst, gateway, kind, active}], включая default.

    default-маршруты (0.0.0.0/0) нужны карте сети: показывают границу с интернетом и
    шлюзы («Континент» активный/резервный). Неактивные маршруты оставляем с
    active=False — это резерв HA; отключённые строки пропускаем (SDD §5.10).
    """

    def flag(value) -> bool:
        # RouterOS API отдаёт флаги как bool или строки («true»/«false»)
        return value in (True, "true", "yes", 1)

    result: list[dict] = []
    for row in rows:
        if flag(row.get("disabled")):
            continue
        dst = str(row.get("dst-address", "")).strip()
        if not dst:
            continue
        try:
            network = ipaddress.ip_network(dst, strict=False)
        except ValueError:
            continue
        if flag(row.get("connected")):
            kind = "connected"
        elif flag(row.get("static")):
            kind = "static"
        else:
            kind = "dynamic"
        result.append(
            {
                "dst": str(network),
                "gateway": str(row.get("gateway", "")).strip(),
                "kind": kind,
                "active": flag(row.get("active")),
            }
        )
    return result


def normalized_addresses(rows: Iterable[Mapping[str, str]]) -> list[dict]:
    """Строки /ip/address → [{address, interface, network}]; disabled/invalid пропускаются."""
    result: list[dict] = []
    for row in rows:
        if str(row.get("disabled")).lower() in ("true", "yes") or str(
            row.get("invalid")
        ).lower() in (
            "true",
            "yes",
        ):
            continue
        address = str(row.get("address", "")).strip()
        try:
            iface = ipaddress.ip_interface(address)
        except ValueError:
            continue
        result.append(
            {
                "address": address,
                "interface": str(row.get("interface", "")).strip(),
                "network": str(iface.network),
            }
        )
    return result


def arp_hosts(rows: Iterable[Mapping[str, str]], cidr: str) -> list[ObservedHost]:
    """ARP-строки → узлы внутри подсети. Пустой/нулевой MAC и не-IP адреса пропускаются."""
    network = ipaddress.ip_network(cidr, strict=False)
    hosts: list[ObservedHost] = []
    for row in rows:
        ip = str(row.get("address", "")).strip()
        mac = str(row.get("mac-address", "")).strip().lower()
        if not ip or not mac or mac == ZERO_MAC:
            continue
        try:
            if ipaddress.ip_address(ip) not in network:
                continue
        except ValueError:
            continue
        hosts.append(ObservedHost(ip=ip, mac=mac, source="mikrotik_api"))
    return hosts


def hostnames_by_mac(leases: Iterable[Mapping[str, str]]) -> dict[str, str]:
    """Имена из DHCP-аренд: MAC → host-name (заглушки вида «-» и пустые пропускаются)."""
    names: dict[str, str] = {}
    for row in leases:
        mac = str(row.get("mac-address", "")).strip().lower()
        name = str(row.get("host-name", "")).strip()
        if mac and name and name != "-":
            names[mac] = name
    return names


def merge_observations(
    observed: list[ObservedHost],
    passive: list[ObservedHost],
    leases: Iterable[Mapping[str, str]] = (),
) -> list[ObservedHost]:
    """Данные nmap главнее: MAC/имя дополняются из ARP/DHCP, узлы только из ARP добавляются.

    Порты и ОС nmap не затираются: у ARP-строки их просто нет.
    """
    names = hostnames_by_mac(leases)
    passive_by_ip = {host.ip: host for host in passive}
    merged: list[ObservedHost] = []
    seen: set[str] = set()
    for host in observed:
        extra = passive_by_ip.get(host.ip)
        mac = host.mac or (extra.mac if extra else None)
        merged.append(replace(host, mac=mac, hostname=host.hostname or names.get(mac or "", "")))
        seen.add(host.ip)
    for host in passive:
        if host.ip in seen:
            continue
        seen.add(host.ip)
        merged.append(replace(host, hostname=names.get(host.mac or "", "")))
    return merged
