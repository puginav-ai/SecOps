"""Определение ОС без учётных данных: SMB/RDP-скрипты nmap (SDD §5.10).

`smb-os-discovery` отдаёт строку вида «Windows 10 Pro 15063» и имя компьютера,
`rdp-ntlm-info` — только номер сборки (Product_Version), по нему даём ближайшее имя.
Скрипты работают по анонимному SMB/RDP-хендшейку: пароли не нужны.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# Номер сборки Windows → понятное имя. Для неоднозначных сборок (клиент/сервер)
# пишем оба варианта: точнее скажет строка smb-os-discovery, если SMB открыт.
WINDOWS_BUILDS: dict[str, str] = {
    "6.1.7601": "Windows 7 SP1",
    "6.2.9200": "Windows 8",
    "6.3.9600": "Windows 8.1",
    "10.0.10240": "Windows 10 1507",
    "10.0.10586": "Windows 10 1511",
    "10.0.14393": "Windows 10 1607 / Server 2016",
    "10.0.15063": "Windows 10 1703",
    "10.0.16299": "Windows 10 1709",
    "10.0.17134": "Windows 10 1803",
    "10.0.17763": "Windows 10 1809 / Server 2019",
    "10.0.18362": "Windows 10 1903",
    "10.0.18363": "Windows 10 1909",
    "10.0.19041": "Windows 10 2004",
    "10.0.19042": "Windows 10 20H2",
    "10.0.19043": "Windows 10 21H1",
    "10.0.19044": "Windows 10 21H2",
    "10.0.19045": "Windows 10 22H2",
    "10.0.20348": "Windows Server 2022",
    "10.0.22000": "Windows 11 21H2",
    "10.0.22621": "Windows 11 22H2",
    "10.0.22631": "Windows 11 23H2",
    "10.0.26100": "Windows 11 24H2 / Server 2025",
}


def build_os_probe_args(targets: list[str]) -> list[str]:
    """Nmap с NSE-скриптами SMB/RDP: только эти два порта, без определения портов заново."""
    return [
        "nmap",
        "-n",
        "-Pn",
        "-T3",
        "-p",
        "445,3389",
        "--script",
        "smb-os-discovery,rdp-ntlm-info",
        "--host-timeout",
        "30s",
        "--max-rate",
        "300",
        *targets,
    ]


def _elem(script: ET.Element, key: str) -> str:
    el = script.find(f"elem[@key='{key}']")
    return (el.text or "").strip() if el is not None else ""


def parse_os_probe_xml(xml_text: str) -> dict[str, dict]:
    """XML nmap → {ip: {"os": "Windows 10 Pro 15063", "hostname": "PC39"}}."""
    root = ET.fromstring(xml_text)  # noqa: S314 — XML от нашего subprocess, не из сети
    result: dict[str, dict] = {}
    for host in root.findall("host"):
        status = host.find("status")
        if status is None or status.get("state") != "up":
            continue
        address = host.find("address[@addrtype='ipv4']")
        ip = address.get("addr", "") if address is not None else ""
        if not ip:
            continue
        info: dict[str, str] = {}
        for script in host.findall("hostscript/script"):
            script_id = script.get("id", "")
            if script_id == "smb-os-discovery":
                lanmanager = _elem(script, "lanmanager").lower()
                os_name = _elem(script, "os").split(" (")[0].strip()
                # Samba отдаёт «Windows 6.1» как версию протокола — это Linux, не Windows
                if os_name and "samba" not in lanmanager:
                    info["os"] = os_name
                hostname = _elem(script, "server") or _elem(script, "fqdn")
                if hostname:
                    # SMB отдаёт имя с завершающим NUL (иногда литералом «\x00»/«\00»)
                    info["hostname"] = re.sub(r"\\x00|\\00$", "", hostname).strip()
            elif script_id == "rdp-ntlm-info" and "os" not in info:
                version = _elem(script, "Product_Version")
                if version:
                    info["os"] = WINDOWS_BUILDS.get(version, f"Windows (сборка {version})")
                hostname = _elem(script, "NetBIOS_Computer_Name")
                if hostname:
                    info["hostname"] = hostname
        if info:
            result[ip] = info
    return result
