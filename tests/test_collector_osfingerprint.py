"""SMB/RDP-зонд ОС без учётных данных (SDD §5.10)."""

from __future__ import annotations

from collector.osfingerprint import build_os_probe_args, parse_os_probe_xml

SMB_XML = """<?xml version="1.0"?><nmaprun>
  <host><status state="up"/><address addr="10.60.1.50" addrtype="ipv4"/>
    <hostscript><script id="smb-os-discovery">
      <elem key="os">Windows 10 Pro 15063</elem>
      <elem key="server">PC39</elem>
    </script></hostscript>
  </host>
</nmaprun>"""

RDP_XML = """<?xml version="1.0"?><nmaprun>
  <host><status state="up"/><address addr="10.60.1.51" addrtype="ipv4"/>
    <hostscript><script id="rdp-ntlm-info">
      <elem key="Product_Version">10.0.17763</elem>
      <elem key="NetBIOS_Computer_Name">SRV-DC</elem>
    </script></hostscript>
  </host>
</nmaprun>"""


def test_parse_smb_version_and_hostname():
    assert parse_os_probe_xml(SMB_XML) == {
        "10.60.1.50": {"os": "Windows 10 Pro 15063", "hostname": "PC39"}
    }


def test_parse_rdp_build_without_smb():
    assert parse_os_probe_xml(RDP_XML) == {
        "10.60.1.51": {"os": "Windows 10 1809 / Server 2019", "hostname": "SRV-DC"}
    }


def test_parse_samba_is_not_windows():
    """Samba отдаёт «Windows 6.1» как версию SMB-протокола — ОС не Windows."""
    xml = """<?xml version="1.0"?><nmaprun>
      <host><status state="up"/><address addr="10.60.1.52" addrtype="ipv4"/>
        <hostscript><script id="smb-os-discovery">
          <elem key="os">Windows 6.1</elem>
          <elem key="lanmanager">Samba 4.9.4-Debian</elem>
          <elem key="server">LOR-ZAV</elem>
        </script></hostscript>
      </host>
    </nmaprun>"""

    assert parse_os_probe_xml(xml) == {"10.60.1.52": {"hostname": "LOR-ZAV"}}


def test_build_os_probe_args_uses_scripts_and_two_ports():
    args = build_os_probe_args(["10.60.1.50"])

    assert "--script" in args
    assert "smb-os-discovery,rdp-ntlm-info" in args
    assert args[args.index("-p") + 1] == "445,3389"
    assert args[-1] == "10.60.1.50"
