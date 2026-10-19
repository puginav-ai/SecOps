"""Классификатор типа устройства по портам/вендору/имени (SDD §5.10)."""

from __future__ import annotations

from collector.classify import classify_role


def test_network_vendor_wins():
    assert classify_role([], vendor="Routerboard.com") == "network"
    assert classify_role([80], vendor="Cisco Systems, Inc") == "network"


def test_printer_ports_and_vendor():
    assert classify_role([9100]) == "printer"
    assert classify_role([631, 80]) == "printer"
    assert classify_role([80, 443], vendor="HP") == "printer"
    assert classify_role([80, 443], vendor="Hewlett Packard") == "printer"


def test_medical_by_dicom_ports():
    assert classify_role([104]) == "medical"
    assert classify_role([11112, 443]) == "medical"


def test_phones_and_cameras():
    assert classify_role([5060]) == "phone"
    assert classify_role([], vendor="Yealink Network Technology") == "phone"
    assert classify_role([554, 80]) == "camera"


def test_servers_and_workstations_by_ports():
    assert classify_role([22, 80, 443]) == "server"
    assert classify_role([1433]) == "server"
    assert classify_role([3389, 445, 135]) == "workstation"


def test_hostname_hints_are_weak():
    assert classify_role([], hostname="srv-lis") == "server"
    assert classify_role([], hostname="prn-2floor") == "printer"
    assert classify_role([], hostname="ivanov-pc") == "workstation"
    # порты сильнее имени: сервер с именем АРМ остаётся сервером
    assert classify_role([22, 443], hostname="ivanov-pc") == "server"


def test_unknown_stays_empty():
    assert classify_role([]) == ""
    assert classify_role([], vendor="Неизвестный вендор", hostname="host-1") == ""
