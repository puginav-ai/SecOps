"""Скан сегмента: журнал запусков, профили, отказы, ошибки (SDD §5.2)."""

from __future__ import annotations

import pytest
from freezegun import freeze_time

from apps.discovery import tasks
from apps.discovery.models import ScanRun
from apps.discovery.tests.samples import DETAIL_XML, SWEEP_XML
from apps.registry.models import Asset, Segment, Site
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


@freeze_time("2026-10-12 23:30:00+03:00")
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


@freeze_time("2026-10-12 23:30:00+03:00")
def test_top100_profile_enriches_ports_and_os(segment: Segment, monkeypatch) -> None:
    segment.scan_profile = Segment.ScanProfile.TOP100
    segment.save(update_fields=["scan_profile"])
    calls = patch_nmap(monkeypatch, [SWEEP_XML, DETAIL_XML])

    tasks.scan_segment(segment.pk)

    assert len(calls) == 2
    assert "--top-ports" in calls[1]
    srv = Asset.objects.get(ip="10.60.1.10")
    assert (srv.ports, srv.os_name, srv.hostname) == ([22, 443], "Linux 5.4", "srv-demo")


@freeze_time("2026-10-12 23:30:00+03:00")
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


@freeze_time("2026-10-12 23:30:00+03:00")
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


@freeze_time("2026-10-12 23:30:00+03:00")
def test_scan_due_segments_scans_once_per_interval(segment: Segment, monkeypatch) -> None:
    patch_nmap(monkeypatch, [SWEEP_XML])

    assert tasks.scan_due_segments() == 1
    assert ScanRun.objects.count() == 1

    assert tasks.scan_due_segments() == 0  # только что просканирован — не дублируем
    assert ScanRun.objects.count() == 1


@freeze_time("2026-10-12 12:00:00+03:00")
def test_scan_due_segments_does_nothing_outside_window(segment: Segment, monkeypatch) -> None:
    forbid_nmap(monkeypatch)

    assert tasks.scan_due_segments() == 0
    assert ScanRun.objects.count() == 0
