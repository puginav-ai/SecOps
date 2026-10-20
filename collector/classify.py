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
DATABASE_PORTS = {1433, 1521, 3306, 5432, 9200, 27017, 6379}
# Службы, которых не бывает на рядовом АРМ: AD, почта, БД. Проверяются до Windows-портов,
# иначе контроллер домена с 445 попадёт в «АРМ».
SERVER_SIGNAL_PORTS = DATABASE_PORTS | {25, 53, 88, 389, 636, 3268, 3269, 587, 993, 995}
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
# Точки доступа: в этой сети Wi-Fi держат бытовые роутеры (TL-WR840N, Archer, Keenetic,
# DIR-300, Tenda, UniFi). Модель в имени хоста — сильный признак; по одному вендору
# TP-Link/D-Link не отличить AP от коммутатора, поэтому вендор решает только для
# производителей, у которых AP/роутеры — основной профиль (SDD §5.10).
AP_HOSTNAME_RE = re.compile(
    r"(tl-w[rda]\d|archer|^ec\d{3}[-_ ]?g|dir-\d|keenetic|unifi|uap[-_]|aircube|"
    r"tenda|access[-_ ]point|wifi[-_ ]ap|^f9\d{2})",
    re.IGNORECASE,
)
AP_VENDORS = ("keenetic", "ubiquiti", "tenda")
# Личные смартфоны/планшеты (SDD §5.10): для реестра это находка «личное устройство
# в рабочем VLAN», а не техника больницы. Huawei/ZTE сюда не входят: по одному вендору
# их коммутатор не отличить от телефона — телефон ловится по имени из DHCP.
MOBILE_HOSTNAME_RE = re.compile(
    r"^(iphone|ipad|redmi|poco|xiaomi|mi-\d|galaxy|sm-[agsnm]\d|honor|"
    r"huawei[-_ ]?(p\d|p-?\d|mate|nova)|android-[0-9a-f]{8,}|realme|oppo|vivo|"
    r"oneplus|pixel|moto[ -]|meizu|tecno|infinix|nothing[ -]phone)",
    re.IGNORECASE,
)
MOBILE_VENDORS = (
    "xiaomi",
    "apple",
    "samsung electronics",
    "honor",
    "oppo",
    "vivo",
    "oneplus",
    "realme",
    "meizu",
    "motorola",
    "google llc",
)
# Потребительские PC-производители: материнские платы и моноблоки, т.е. рабочие места.
# Dell/HP/Lenovo/Apple сюда не входят — у них есть и серверы; им нужны порты или имя.
WORKSTATION_VENDORS = (
    "asrock",
    "giga-byte",
    "gigabyte",
    "micro-star",
    "biostar",
    "asustek",
    "pc aquarius",
    "aquarius",
    "aio lcd pc",
    "tpv",
    "acer",
)
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
    # Аппаратные шлюзы безопасности («Континент» Кода Безопасности) регистрировались
    # как New platforms LLC, Варшавское шоссе, 35 — это тоже сетевое оборудование.
    "new platforms",
)


def derive_os_family(ports: Iterable[int], vendor: str = "") -> str:
    """Семейство ОС по портам/вендору, когда точная ОС не определена.

    Это подсказка, а не точная ОС — в подписи так и пишем «(по портам)»; точная ОС
    появится из SMB/RDP-зонда (Windows) или SSH-баннера (дистрибутив Linux) — SDD §5.10.
    """
    port_set = {int(port) for port in (ports or ()) if str(port).isdigit()}
    vendor_l = (vendor or "").lower()
    if port_set & {8291, 830} or any(marker in vendor_l for marker in ("routerboard", "mikrotik")):
        return "RouterOS"
    if port_set & {135, 139, 445, 3389}:
        return "Windows (по портам)"
    if port_set & {22, 111}:
        return "Linux/Unix (по портам)"
    return ""


def distro_from_services(services: Iterable[dict]) -> str:
    """Дистрибутив Linux из баннера SSH/HTTP-служб: «astra» → Astra Linux, «ubuntu» → Ubuntu.

    OpenSSH в Astra отдаёт версию вида «7.4p1 Debian 10+deb9u6astra6» — по ней и опознаём
    дистрибутив без доступа к хосту. RED OS обычно отдаёт чистый OpenSSH без суффикса,
    поэтому для него нужен SSH-доступ (чтение /etc/os-release) — SDD §5.10.
    """
    text = " ".join(
        f"{item.get('product', '')} {item.get('version', '')} {item.get('extrainfo', '')}"
        for item in services or ()
    ).lower()
    for marker, name in (
        ("astra", "Astra Linux"),
        ("redos", "RED OS"),
        ("red os", "RED OS"),
        ("ubuntu", "Ubuntu"),
        ("debian", "Debian"),
        ("centos", "CentOS"),
        ("almalinux", "AlmaLinux"),
        ("rocky", "Rocky Linux"),
    ):
        if marker in text:
            return name
    return ""


def classify_role(ports: Iterable[int], vendor: str = "", hostname: str = "") -> str:
    """Значение Asset.DeviceRole по портам/вендору/имени; "" — недостаточно признаков."""
    port_set = {int(port) for port in (ports or ()) if str(port).isdigit()}
    vendor_l = (vendor or "").lower()
    name_l = (hostname or "").strip().lower()

    # Личное устройство по имени из DHCP — раньше сетевых вендоров: телефон Huawei
    # по вендору MAC выглядит как сетевое оборудование
    if MOBILE_HOSTNAME_RE.match(name_l):
        return "mobile"
    # Точка доступа по модели в имени — раньше вендоров: TP-Link/D-Link делают и то, и другое
    if AP_HOSTNAME_RE.search(name_l):
        return "ap"
    if any(marker in vendor_l for marker in AP_VENDORS):
        return "ap"
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
    if any(marker in vendor_l for marker in MOBILE_VENDORS):
        return "mobile"

    # AD/БД/почта — сильный признак сервера, проверяем до Windows-портов и веб-морды
    if port_set & SERVER_SIGNAL_PORTS:
        return "server"
    # Материнская плата/моноблок — рабочее место, даже если открыт SSH или 7070 (АРМ с ПО)
    if any(marker in vendor_l for marker in WORKSTATION_VENDORS):
        return "workstation"

    if port_set & NETWORK_PORTS:
        return "network"
    if port_set & CAMERA_PORTS:
        return "camera"
    if port_set & WINDOWS_PORTS:
        return "workstation"
    if port_set & PHONE_PORTS:
        return "phone"

    # Имя хоста — слабый признак: применяем, когда порты ничего не сказали.
    if re.match(r"^(prn|mfp|print|scanner)", name_l):
        return "printer"
    if re.match(r"^(srv|server|dc\d|db\d|sql|lis|pacs)", name_l):
        return "server"
    if re.match(r"^(sw|switch|ap\d|wifi|gw|router)", name_l):
        return "network"
    if re.search(r"(^|[-_.])(pc|arm|wks|workstation)", name_l):
        return "workstation"

    # Открытые только SSH/веб/7070 — слишком слабый признак: оставляем «не определено»,
    # иначе половина АРМ с локальной веб-мордой попадает в серверы.
    return ""
