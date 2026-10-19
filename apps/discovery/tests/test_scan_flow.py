"""Скан сегмента: журнал запусков, профили, отказы, ошибки (SDD §5.2)."""

from __future__ import annotations

import pytest
from freezegun import freeze_time

from apps.discovery import tasks
from apps.discovery.models import ScanRun
from apps.discovery.tests.samples import DETAIL_XML, SWEEP_XML
from apps.registry.models import Asset, Segment, Site
from collector.mikrotik import RouterData
from collector.runner import ScanError

pytestmark = pytest.mark.django_db


@pytest.fixture
def segment() -> Segment:
    site = Site.objects.create(name="Площадка-Демо")
    return Segment.objects.create(
        site=site, name="Сегмент-Демо", cidr="10.60.1.0/24", scan_enabled=True
    )


def patch_nmap(monkeypatch, outputs: list[str]) -> list[list[str]]:
    """Подменяет внешний процесс: возвращает список полученных аргументов."""
    calls: list[list[str]] = []

    def fake(args: list[str], timeout: int = 600) -> str:
        calls.append(args)
        return outputs.pop(0)

    monkeypatch.setattr("apps.discovery.scanner.run_nmap", fake)
    return calls


def forbid_nmap(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("nmap не должен запускаться")

    monkeypatch.setattr("apps.discovery.scanner.run_nmap", boom)


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_creates_run_assets_and_updates_segment(segment: Segment, monkeypatch) -> None:
    calls = patch_nmap(monkeypatch, [SWEEP_XML])

    result = tasks.scan_segment(segment.pk)

    assert result["status"] == "ok"
    run = ScanRun.objects.get()
    assert run.status == ScanRun.Status.OK
    assert run.finished_at is not None
    assert (run.stats["seen"], run.stats["new"]) == (2, 2)
    segment.refresh_from_db()
    assert segment.last_scan_at is not None
    assert Asset.objects.count() == 2
    assert calls == [["nmap", "-sn", "-n", "-T3", "10.60.1.0/24"]]


@freeze_time("2026-10-12 09:30:00+03:00")
def test_top100_profile_enriches_ports_and_os(segment: Segment, monkeypatch) -> None:
    segment.scan_profile = Segment.ScanProfile.TOP100
    segment.save(update_fields=["scan_profile"])
    calls = patch_nmap(monkeypatch, [SWEEP_XML, DETAIL_XML])

    tasks.scan_segment(segment.pk)

    assert len(calls) == 2
    assert "--top-ports" in calls[1]
    srv = Asset.objects.get(ip="10.60.1.10")
    assert (srv.ports, srv.os_name, srv.hostname) == ([22, 443], "Linux 5.4", "srv-demo")


@freeze_time("2026-10-12 09:30:00+03:00")
def test_services_profile_runs_version_stage_on_open_ports(segment: Segment, monkeypatch) -> None:
    """Профиль с версиями: быстрый top-100, затем -sV по объединению открытых портов."""
    segment.scan_profile = Segment.ScanProfile.TOP100_SERVICES
    segment.save(update_fields=["scan_profile"])
    calls = patch_nmap(monkeypatch, [SWEEP_XML, DETAIL_XML, DETAIL_XML])

    tasks.scan_segment(segment.pk)

    assert len(calls) == 3
    version_args = calls[2]
    assert "-sV" in version_args
    assert version_args[version_args.index("-p") + 1] == "22,443,3389"

    srv = Asset.objects.get(ip="10.60.1.10")
    assert "nginx" in srv.software and "OpenSSH" in srv.software
    assert srv.fingerprint["services"][0]["product"] == "OpenSSH"


@freeze_time("2026-10-12 09:30:00+03:00")
def test_disabled_segment_is_refused_without_scan(segment: Segment, monkeypatch) -> None:
    segment.scan_enabled = False
    segment.save(update_fields=["scan_enabled"])
    forbid_nmap(monkeypatch)

    result = tasks.scan_segment(segment.pk)

    assert result == {"status": "refused", "reason": "scan_disabled"}
    assert ScanRun.objects.count() == 0


@freeze_time("2026-10-13 12:00:00+03:00")  # вторник днём, окно сегмента — ночь понедельника
def test_scan_outside_window_is_refused(segment: Segment, monkeypatch) -> None:
    segment.scan_window = {"days": [0], "start": "23:00", "end": "05:00"}
    segment.save(update_fields=["scan_window"])
    forbid_nmap(monkeypatch)

    result = tasks.scan_segment(segment.pk)

    assert result == {"status": "refused", "reason": "outside_window"}
    assert ScanRun.objects.count() == 0


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_error_marks_run_failed(segment: Segment, monkeypatch) -> None:
    def boom(args, timeout=600):
        raise ScanError("nmap недоступен")

    monkeypatch.setattr("apps.discovery.scanner.run_nmap", boom)

    with pytest.raises(ScanError):
        tasks.scan_segment(segment.pk)

    run = ScanRun.objects.get()
    assert run.status == ScanRun.Status.FAILED
    assert "nmap недоступен" in run.stats["error"]
    segment.refresh_from_db()
    assert segment.last_scan_at is None


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_due_segments_scans_once_per_interval(segment: Segment, monkeypatch) -> None:
    patch_nmap(monkeypatch, [SWEEP_XML])

    assert tasks.scan_due_segments() == 1
    assert ScanRun.objects.count() == 1

    assert tasks.scan_due_segments() == 0  # только что просканирован — не дублируем
    assert ScanRun.objects.count() == 1


@freeze_time("2026-10-12 16:00:00+03:00")
def test_scan_due_segments_does_nothing_outside_window(segment: Segment, monkeypatch) -> None:
    forbid_nmap(monkeypatch)

    assert tasks.scan_due_segments() == 0
    assert ScanRun.objects.count() == 0


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_merges_passive_mikrotik_hosts(segment: Segment, monkeypatch, settings) -> None:
    settings.MIKROTIK_HOST = "192.0.2.2"
    patch_nmap(monkeypatch, [SWEEP_XML])
    monkeypatch.setattr(
        "apps.discovery.scanner.fetch_router_data",
        lambda *args, **kwargs: RouterData(
            arp=(
                {"address": "10.60.1.11", "mac-address": "AA:BB:CC:00:00:11"},
                {"address": "10.60.1.99", "mac-address": "AA:BB:CC:00:00:99"},
            ),
            leases=({"mac-address": "AA:BB:CC:00:00:99", "host-name": "printer-demo"},),
        ),
    )

    result = tasks.scan_segment(segment.pk)

    assert result["status"] == "ok"
    assert (result["seen"], result["new"]) == (3, 3)
    assert Asset.objects.get(ip="10.60.1.11").mac == "aa:bb:cc:00:00:11"  # MAC из ARP
    passive = Asset.objects.get(ip="10.60.1.99")  # чисто пассивный узел (nmap его не видел)
    assert (passive.hostname, passive.mac) == ("printer-demo", "aa:bb:cc:00:00:99")
    assert passive.discovery_source == Asset.Source.MIKROTIK_API  # источник — роутер, а не nmap


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_survives_router_outage(segment: Segment, monkeypatch, settings) -> None:
    settings.MIKROTIK_HOST = "192.0.2.2"
    patch_nmap(monkeypatch, [SWEEP_XML])

    def boom(*args, **kwargs):
        raise OSError("router unreachable")

    monkeypatch.setattr("apps.discovery.scanner.fetch_router_data", boom)

    result = tasks.scan_segment(segment.pk)

    assert result["status"] == "ok"  # скан не падает из-за недоступного роутера
    assert Asset.objects.count() == 2


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_skips_router_when_not_configured(segment: Segment, monkeypatch, settings) -> None:
    settings.MIKROTIK_HOST = ""
    patch_nmap(monkeypatch, [SWEEP_XML])

    def boom(*args, **kwargs):
        raise AssertionError("адаптер не должен вызываться без MIKROTIK_HOST")

    monkeypatch.setattr("apps.discovery.scanner.fetch_router_data", boom)

    assert tasks.scan_segment(segment.pk)["status"] == "ok"
    assert Asset.objects.count() == 2


@freeze_time("2026-10-12 09:30:00+03:00")
def test_scan_merges_extra_router_arp(segment: Segment, monkeypatch, settings) -> None:
    """Пассивные данные берутся и со второго настроенного роутера (например, КПЦ)."""
    settings.MIKROTIK_HOST = "192.0.2.2"
    settings.MIKROTIK_EXTRA_ROUTERS = [{"host": "192.0.2.9", "user": "u", "password": "p"}]
    patch_nmap(monkeypatch, [SWEEP_XML])

    def fake(host: str, *args, **kwargs) -> RouterData:
        if host == "192.0.2.9":
            return RouterData(arp=({"address": "10.60.1.99", "mac-address": "AA:BB:CC:00:00:99"},))
        return RouterData(arp=({"address": "10.60.1.11", "mac-address": "AA:BB:CC:00:00:11"},))

    monkeypatch.setattr("apps.discovery.scanner.fetch_router_data", fake)

    result = tasks.scan_segment(segment.pk)

    assert result["status"] == "ok"
    assert (result["seen"], result["new"]) == (3, 3)
    assert Asset.objects.get(ip="10.60.1.99").mac == "aa:bb:cc:00:00:99"  # узел от второго роутера
    assert Asset.objects.get(ip="10.60.1.11").mac == "aa:bb:cc:00:00:11"  # MAC от основного
