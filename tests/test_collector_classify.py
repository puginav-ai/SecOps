"""Классификатор типа устройства по портам/вендору/имени (SDD §5.10)."""

from __future__ import annotations

from collector.classify import (
    better_os_family,
    classify_role,
    derive_os_family,
    distro_from_services,
)


def test_network_vendor_wins():
    assert classify_role([], vendor="Routerboard.com") == "network"
    assert classify_role([80], vendor="Cisco Systems, Inc") == "network"
    # «Континент» Кода Безопасности регистрировал OUI как New platforms LLC
    assert classify_role([], vendor="New platforms LLC") == "network"


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
    assert classify_role([1433]) == "server"
    assert classify_role([53, 88, 389, 445]) == "server"  # контроллер домена, а не АРМ
    assert classify_role([3389, 445, 135]) == "workstation"
    # SSH и веб сами по себе — не признак сервера: локальная веб-морда есть у АРМ и медтехники
    assert classify_role([22, 80, 443]) == ""


def test_workstation_vendor_beats_generic_ports_and_softphone():
    assert classify_role([22, 111, 7070], vendor="ASRock Incorporation") == "workstation"
    assert classify_role([135, 139, 445, 22, 7070], vendor="PC Aquarius") == "workstation"
    assert classify_role([5060, 135, 139, 445], vendor="ASUSTek COMPUTER INC.") == "workstation"


def test_hostname_hints_are_weak():
    assert classify_role([], hostname="srv-lis") == "server"
    assert classify_role([], hostname="prn-2floor") == "printer"
    assert classify_role([], hostname="ivanov-pc") == "workstation"
    # порты сильнее имени, но только сильные: АРМ с SSH не становится сервером
    assert classify_role([22, 443], hostname="ivanov-pc") == "workstation"


def test_mobile_devices_by_hostname_and_vendor():
    assert classify_role([], hostname="iPhone") == "mobile"
    assert classify_role([], hostname="POCO-X7-Pro") == "mobile"
    assert classify_role([], hostname="android-16c6e474f931f1c1") == "mobile"
    assert classify_role([], vendor="Xiaomi Communications Co Ltd") == "mobile"
    assert classify_role([], vendor="Apple, Inc.") == "mobile"
    # Huawei по вендору неоднозначен (коммутаторы и телефоны): сеть решает вендор, телефон — имя
    assert classify_role([], vendor="Huawei Technologies") == "network"
    assert classify_role([], hostname="HUAWEI P30", vendor="Huawei Technologies") == "mobile"
    # Samsung с портами печати остаётся принтером
    assert classify_role([9100], vendor="Samsung Electronics Co.,Ltd") == "printer"


def test_access_points_by_model_and_vendor():
    assert classify_role([], hostname="TL-WR840N") == "ap"
    assert classify_role([], hostname="Keenetic-9976") == "ap"
    assert classify_role([], hostname="Archer_C6", vendor="TP-LINK TECHNOLOGIES CO.,LTD.") == "ap"
    assert classify_role([], hostname="EC220-G5", vendor="TP-LINK TECHNOLOGIES CO.,LTD.") == "ap"
    assert classify_role([], vendor="Ubiquiti Inc") == "ap"
    assert classify_role([], vendor="Tenda Technology Co.,Ltd.Dongguan") == "ap"
    # коммутатор TP-Link по одному вендору остаётся сетевым оборудованием
    assert classify_role([], vendor="TP-LINK TECHNOLOGIES CO.,LTD.") == "network"


def test_os_family_derived_from_ports_when_no_nmap_os():
    assert derive_os_family([135, 445, 3389]) == "Windows (по портам)"
    assert derive_os_family([22, 111]) == "Linux/Unix (по портам)"
    assert derive_os_family([8291]) == "RouterOS"
    assert derive_os_family([], vendor="Routerboard.com") == "RouterOS"
    assert derive_os_family([9100]) == ""


def test_linux_distro_from_ssh_banner():
    assert (
        distro_from_services([{"product": "OpenSSH", "version": "7.4p1 Debian 10+deb9u6astra6"}])
        == "Astra Linux"
    )
    assert distro_from_services([{"version": "10.2p1 Ubuntu 2ubuntu3.8"}]) == "Ubuntu"
    assert distro_from_services([{"version": "OpenSSH 8.7 (RED OS)"}]) == "RED OS"
    assert distro_from_services([{"version": "9.9"}]) == ""


def test_os_family_does_not_downgrade_to_generic():
    assert better_os_family("Astra Linux", "Linux/Unix (по портам)") == "Astra Linux"
    assert better_os_family("Linux/Unix (по портам)", "Astra Linux") == "Astra Linux"
    assert better_os_family("", "Windows (по портам)") == "Windows (по портам)"
    assert better_os_family("Windows (по портам)", "Windows 10 Pro") == "Windows 10 Pro"


def test_server_requires_real_signals():
    # один порт каталога/SSH/web — ещё не сервер
    assert classify_role([22]) == ""
    assert classify_role([23, 80]) == ""
    assert classify_role([389]) == ""
    # набор AD-портов или серверная ОС — сервер
    assert classify_role([53, 88, 389, 445]) == "server"
    assert classify_role([135, 139, 445, 1433, 3389], os_name="Windows Server 2019") == "server"
    # Windows 10/11 с локальной MySQL — рабочее место
    assert (
        classify_role([135, 139, 445, 3306, 5357, 7070], os_name="Windows 10 Pro 19045")
        == "workstation"
    )
    # почтовый сервер — только с набором почтовых портов
    assert classify_role([25, 110, 143]) == "server"


def test_unknown_stays_empty():
    assert classify_role([]) == ""
    assert classify_role([], vendor="Неизвестный вендор", hostname="host-1") == ""
