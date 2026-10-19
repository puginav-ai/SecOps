"""Чистая логика collector: парсинг nmap XML, чанки сегмента, бюджет скана (SDD §5.2)."""

from __future__ import annotations

from apps.discovery.tests.samples import DETAIL_XML, SWEEP_XML, WEIRD_XML
from collector.nmap import (
    HOST_TIMEOUT,
    MAX_RATE,
    TOP_PORTS,
    VERSION_HOST_TIMEOUT,
    build_service_args,
    build_sweep_args,
    chunk_cidr,
    parse_nmap_xml,
)


def test_sweep_xml_yields_only_alive_hosts_with_normalized_mac():
    hosts = parse_nmap_xml(SWEEP_XML)

    assert [host.ip for host in hosts] == ["10.60.1.10", "10.60.1.11"]
    assert hosts[0].mac == "aa:bb:cc:00:00:01"
    assert hosts[1].mac is None
    assert all(host.source == "nmap" for host in hosts)


def test_detail_xml_yields_ports_hostname_and_os():
    hosts = {host.ip: host for host in parse_nmap_xml(DETAIL_XML)}

    assert hosts["10.60.1.10"].ports == (22, 443)  # закрытый 80 не попадает
    assert hosts["10.60.1.10"].hostname == "srv-demo"
    assert hosts["10.60.1.10"].os_name == "Linux 5.4"
    assert hosts["10.60.1.11"].ports == (3389,)


def test_detail_xml_yields_services_and_versions():
    hosts = {host.ip: host for host in parse_nmap_xml(DETAIL_XML)}

    ssh = hosts["10.60.1.10"].services[0]
    assert ssh == {
        "port": 22,
        "service": "ssh",
        "product": "OpenSSH",
        "version": "8.9p1",
        "extrainfo": "",
    }
    assert hosts["10.60.1.11"].services[0]["service"] == "ms-wbt-server"


def test_sweep_xml_has_no_services():
    assert all(host.services == () for host in parse_nmap_xml(SWEEP_XML))


def test_weird_xml_is_survived():
    hosts = parse_nmap_xml(WEIRD_XML)

    assert len(hosts) == 1
    assert hosts[0].ip == "10.60.1.77"
    assert hosts[0].mac == "aa:bb:cc:00:00:77"
    assert hosts[0].ports == ()


def test_chunk_cidr_splits_into_slash24():
    assert chunk_cidr("10.60.1.0/24") == ["10.60.1.0/24"]
    assert chunk_cidr("10.60.0.0/23") == ["10.60.0.0/24", "10.60.1.0/24"]
    assert chunk_cidr("10.60.1.7/24") == ["10.60.1.0/24"]  # хост-биты нормализуются


def test_sweep_args_are_careful():
    assert build_sweep_args("10.60.1.0/24") == ["nmap", "-sn", "-n", "-T3", "10.60.1.0/24"]


def test_service_args_respect_scan_budget():
    args = build_service_args(["10.60.1.10", "10.60.1.11"])

    assert args[:3] == ["nmap", "-n", "-T3"]
    assert "--top-ports" in args and TOP_PORTS in args
    assert "--host-timeout" in args and HOST_TIMEOUT in args
    assert "--max-rate" in args and MAX_RATE in args
    assert args[-2:] == ["10.60.1.10", "10.60.1.11"]


def test_version_service_args_add_fingerprinting():
    args = build_service_args(["10.60.1.10"], version=True)

    assert "-sV" in args
    assert "--version-light" in args
    assert "banner,http-title" in args
    assert VERSION_HOST_TIMEOUT in args
    assert args[-1] == "10.60.1.10"
