"""OUI-вендор по MAC: оффлайн-таблица IEEE в репозитории (SDD §5.10)."""

from __future__ import annotations

from collector.oui import normalize_mac, vendor_for_mac


def test_normalize_mac_accepts_common_formats():
    assert normalize_mac("AA:BB:CC:00:00:01") == "AABBCC000001"
    assert normalize_mac("aa-bb-cc-00-00-01") == "AABBCC000001"
    assert normalize_mac("aabb.cc00.0001") == "AABBCC000001"
    assert normalize_mac("") == ""
    assert normalize_mac("не-mac") == ""


def test_vendor_lookup_by_oui_prefix():
    # префиксы из публичной таблицы IEEE: MikroTik (Organization Name "Routerboard.com") и VMware
    assert "routerboard" in vendor_for_mac("08:55:31:AA:BB:CC").lower()
    assert "vmware" in vendor_for_mac("00:0c:29:11:22:33").lower()


def test_unknown_mac_has_no_vendor():
    assert vendor_for_mac("") == ""
    assert vendor_for_mac("ff:ff:ff:ff:ff:ff") == ""
