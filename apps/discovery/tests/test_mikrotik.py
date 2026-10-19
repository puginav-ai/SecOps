"""Mikrotik (RouterOS API): чистые преобразования, слияние с nmap и контракт вызова (SDD §5.2)."""

from __future__ import annotations

import ssl

import pytest

from collector.mikrotik import (
    RouterData,
    arp_hosts,
    fetch_router_data,
    hostnames_by_mac,
    merge_observations,
)
from collector.nmap import ObservedHost

# Вымышленные строки роутера (/ip/arp). Реальных сетей и данных здесь нет.
ARP_ROWS = [
    {"address": "10.60.1.10", "mac-address": "AA:BB:CC:00:00:01", "interface": "bridge"},
    {"address": "10.60.1.11", "mac-address": "aa:bb:cc:00:00:02"},
    {"address": "10.60.1.99", "mac-address": "AA:BB:CC:00:00:99"},
    {"address": "10.60.9.9", "mac-address": "AA:BB:CC:00:00:09"},  # вне подсети сегмента
    {"address": "", "mac-address": "AA:BB:CC:00:00:00"},  # без адреса
    {"address": "10.60.1.12", "mac-address": "00:00:00:00:00:00"},  # MAC не определён
    {"address": "не-ip", "mac-address": "AA:BB:CC:00:00:05"},
]

# Вымышленные строки роутера (/ip/dhcp-server/lease), из них одна — «waiting»
LEASE_ROWS = [
    {"mac-address": "AA:BB:CC:00:00:99", "host-name": "printer-demo", "status": "bound"},
    {"mac-address": "AA:BB:CC:00:00:05", "host-name": "-", "status": "bound"},
    {"mac-address": "AA:BB:CC:00:00:06", "status": "bound"},
]


def test_arp_hosts_keeps_only_valid_addresses_inside_cidr() -> None:
    hosts = arp_hosts(ARP_ROWS, "10.60.1.0/24")

    assert [(h.ip, h.mac, h.source) for h in hosts] == [
        ("10.60.1.10", "aa:bb:cc:00:00:01", "mikrotik_api"),
        ("10.60.1.11", "aa:bb:cc:00:00:02", "mikrotik_api"),
        ("10.60.1.99", "aa:bb:cc:00:00:99", "mikrotik_api"),
    ]


def test_hostnames_by_mac_skips_placeholder_and_empty() -> None:
    assert hostnames_by_mac(LEASE_ROWS) == {"aa:bb:cc:00:00:99": "printer-demo"}


def test_merge_enriches_nmap_and_adds_passive_hosts() -> None:
    observed = [
        ObservedHost(ip="10.60.1.10", ports=(22,)),  # MAC придёт из ARP
        ObservedHost(ip="10.60.1.11", mac="aa:bb:cc:00:00:02", hostname="nmap-name", ports=(3389,)),
    ]

    merged = merge_observations(observed, arp_hosts(ARP_ROWS, "10.60.1.0/24"), LEASE_ROWS)
    by_ip = {host.ip: host for host in merged}

    assert len(merged) == 3
    assert (by_ip["10.60.1.10"].mac, by_ip["10.60.1.10"].ports) == ("aa:bb:cc:00:00:01", (22,))
    assert by_ip["10.60.1.11"].hostname == "nmap-name"  # имя nmap главнее DHCP
    # узел, который nmap не увидел (ICMP закрыт), добавлен из ARP и назван DHCP-арендой
    assert (by_ip["10.60.1.99"].source, by_ip["10.60.1.99"].hostname) == (
        "mikrotik_api",
        "printer-demo",
    )


def test_fetch_router_data_reads_arp_and_bound_leases(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeApi:
        def __init__(self, kwargs: dict[str, object]) -> None:
            calls["connect_kwargs"] = kwargs
            calls["closed"] = False
            calls["paths"] = []

        def path(self, *parts: str):
            calls["paths"].append(parts)
            if parts[:2] == ("ip", "arp"):
                return iter([{"address": "10.0.0.1", "mac-address": "AA:BB:CC:00:00:01"}])
            if parts == ("ip", "dhcp-server", "lease"):
                return iter(
                    [
                        {"mac-address": "AA:BB:CC:00:00:01", "host-name": "pc", "status": "bound"},
                        {
                            "mac-address": "AA:BB:CC:00:00:02",
                            "host-name": "old",
                            "status": "waiting",
                        },
                    ]
                )
            if parts == ("system", "identity"):
                return iter([{"name": "MT-Root"}])
            if parts == ("ip", "address"):
                return iter([{"address": "10.0.0.1/24", "interface": "bridge"}])
            if parts == ("ip", "neighbor"):
                return iter(
                    [
                        {
                            "address": "192.168.253.1",
                            "identity": "MT-Pol",
                            "interface": "sfp1",
                            "platform": "MikroTik",
                            "mac-address": "AA:BB:CC:00:00:02",
                        }
                    ]
                )
            return iter(())

        def close(self) -> None:
            calls["closed"] = True

    def fake_connect(host: str, username: str, password: str, **kwargs: object) -> FakeApi:
        calls["auth"] = (host, username, password)
        return FakeApi(kwargs)

    monkeypatch.setattr("librouteros.connect", fake_connect)

    data = fetch_router_data("192.0.2.2", "admin", "demo-fake-password")

    assert calls["auth"] == ("192.0.2.2", "admin", "demo-fake-password")
    assert calls["connect_kwargs"] == {"port": 8728, "timeout": 10.0}
    assert calls["paths"] == [
        ("ip", "arp"),
        ("ip", "dhcp-server", "lease"),
        ("system", "identity"),
        ("ip", "address"),
        ("ip", "neighbor"),
    ]
    assert calls["closed"] is True
    assert data.arp == ({"address": "10.0.0.1", "mac-address": "AA:BB:CC:00:00:01"},)
    # «waiting»-аренда не попадает: интересны только действующие устройства
    assert data.leases == (
        {"mac-address": "AA:BB:CC:00:00:01", "host-name": "pc", "status": "bound"},
    )
    assert data.identity == "MT-Root"
    assert data.addresses == ({"address": "10.0.0.1/24", "interface": "bridge"},)
    assert data.neighbors[0]["identity"] == "MT-Pol"


def test_fetch_router_data_uses_api_ssl_port(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeApi:
        def path(self, *parts: str):
            return iter(())

        def close(self) -> None:
            pass

    def fake_connect(host: str, username: str, password: str, **kwargs: object) -> FakeApi:
        captured.update(kwargs)
        return FakeApi()

    monkeypatch.setattr("librouteros.connect", fake_connect)

    data = fetch_router_data("192.0.2.2", "admin", "x", use_ssl=True)

    assert data == RouterData()
    assert captured["port"] == 8729
    context = captured["ssl_wrapper"]
    assert isinstance(context, ssl.SSLContext)
    # роутер в контуре — с самоподписанным сертификатом, проверку цепочки не проходим
    assert (context.check_hostname, context.verify_mode) == (False, ssl.CERT_NONE)
