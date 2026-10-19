"""Автоклассификация устройства по сетевым признакам (SDD §5.10, роль `role_auto`).

Правила детерминированные, первое совпадение выигрывает. Вход — только то, что реально
собирает discovery: открытые порты, вендор по MAC (OUI), имя хоста. Пустая строка — «не
определено»; ручное значение `device_role` в реестре главнее автоматического.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MEDICAL_PORTS = {104, 11112, 2762}  # DICOM / медоборудование
PRINTER_PORTS = {9100, 631, 515}  # raw-печать, IPP, LPD
NETWORK_PORTS = {161, 162, 8291, 830}  # SNMP, Winbox, NETCONF
PHONE_PORTS = {5060, 5061}  # SIP
CAMERA_PORTS = {554, 8554}  # RTSP
DATABASE_PORTS = {1433, 1521, 3306, 5432, 9200}
SERVER_PORTS = {22, 80, 443, 8080, 8443}
WINDOWS_PORTS = {135, 139, 445, 3389}

PRINTER_VENDORS = (
    "hp",
    "hewlett",
    "canon",
    "brother",
    "epson",
    "kyocera",
    "xerox",
    "ricoh",
    "lexmark",
)
PHONE_VENDORS = ("yealink", "polycom", "grandstream", "avaya", "fanvil", "snom")
NETWORK_VENDORS = (
    "mikrotik",
    "routerboard",
    "cisco",
    "huawei",
    "aruba",
    "ubiquiti",
    "tp-link",
    "d-link",
    "juniper",
    "eltex",
    "zyxel",
    "extreme networks",
)


def classify_role(ports: Iterable[int], vendor: str = "", hostname: str = "") -> str:
    """Значение Asset.DeviceRole по портам/вендору/имени; "" — недостаточно признаков."""
    port_set = {int(port) for port in (ports or ()) if str(port).isdigit()}
    vendor_l = (vendor or "").lower()
    name_l = (hostname or "").strip().lower()

    if any(marker in vendor_l for marker in NETWORK_VENDORS):
        return "network"
    if port_set & PRINTER_PORTS:
        return "printer"
    if any(marker in vendor_l for marker in PRINTER_VENDORS) and port_set & (
        PRINTER_PORTS | {80, 443}
    ):
        return "printer"
    if port_set & MEDICAL_PORTS:
        return "medical"
    if any(marker in vendor_l for marker in PHONE_VENDORS):
        return "phone"
    if port_set & NETWORK_PORTS:
        return "network"
    if port_set & PHONE_PORTS:
        return "phone"
    if port_set & CAMERA_PORTS:
        return "camera"

    # Серверные порты — сильный признак: проверяем до слабых подсказок имени.
    if port_set & DATABASE_PORTS:
        return "server"
    if port_set & SERVER_PORTS:
        return "server"

    # Имя хоста — слабый признак: применяем, когда порты ничего не сказали.
    if re.match(r"^(prn|mfp|print|scanner)", name_l):
        return "printer"
    if re.match(r"^(srv|server|dc\d|db\d|sql|lis|pacs)", name_l):
        return "server"
    if re.match(r"^(sw|switch|ap\d|wifi|gw|router)", name_l):
        return "network"
    if re.search(r"(^|[-_.])(pc|arm|wks|workstation)", name_l):
        return "workstation"

    if port_set & WINDOWS_PORTS:
        return "workstation"
    return ""
