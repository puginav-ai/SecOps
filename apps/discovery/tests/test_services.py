"""Upsert активов: MAC-first идентичность, IP-reuse, дрейф, анти-мигание (SDD §5.2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.discovery import services
from apps.registry.models import Asset, AssetEvent, Segment, Site
from collector.nmap import ObservedHost

pytestmark = pytest.mark.django_db

MAC_A = "aa:bb:cc:00:00:01"
MAC_B = "aa:bb:cc:00:00:02"


@pytest.fixture
def segment() -> Segment:
    site = Site.objects.create(name="Площадка-Демо")
    return Segment.objects.create(
        site=site, name="Сегмент-Демо", cidr="10.60.1.0/24", scan_enabled=True
    )


def host(
    ip: str, mac: str | None = None, hostname: str = "", ports: tuple[int, ...] = ()
) -> ObservedHost:
    return ObservedHost(ip=ip, mac=mac, hostname=hostname, ports=ports)


# --- upsert активов -------------------------------------------------------------------


def test_new_hosts_become_assets_with_new_events(segment: Segment) -> None:
    result = services.apply_observations(
        segment,
        [host("10.60.1.10", mac=MAC_A, hostname="srv-demo"), host("10.60.1.11")],
    )

    assert (result.seen, result.new) == (2, 2)
    assets = list(Asset.objects.order_by("ip"))
    assert [asset.ip for asset in assets] == ["10.60.1.10", "10.60.1.11"]
    srv = assets[0]
    assert (srv.mac, srv.hostname, srv.segment_id, srv.site_id) == (
        MAC_A,
        "srv-demo",
        segment.pk,
        segment.site_id,
    )
    assert srv.miss_count == 0
    assert srv.last_seen_at is not None
    assert AssetEvent.objects.filter(kind=AssetEvent.Kind.NEW).count() == 2


@freeze_time("2026-10-12 09:30:00+03:00")
def test_same_mac_and_ip_only_updates_last_seen(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
    with freeze_time("2026-10-12 23:40:00+03:00"):
        result = services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])

    asset = Asset.objects.get()
    assert timezone.localtime(asset.last_seen_at).minute == 40
    assert (result.new, result.changed, result.disappeared) == (0, 0, 0)
    assert AssetEvent.objects.count() == 1  # только «обнаружен»


def test_mac_first_identity_follows_ip_change(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
    services.apply_observations(segment, [host("10.60.1.50", mac=MAC_A)])

    asset = Asset.objects.get()
    assert asset.ip == "10.60.1.50"
    assert AssetEvent.objects.get(kind=AssetEvent.Kind.CHANGED).details == {
        "ip": {"from": "10.60.1.10", "to": "10.60.1.50"}
    }


def test_ip_reuse_closes_old_asset_and_creates_new(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
    result = services.apply_observations(segment, [host("10.60.1.10", mac=MAC_B)])

    assert (result.new, result.disappeared) == (1, 1)
    old = Asset.objects.get(mac=MAC_A)
    new = Asset.objects.get(mac=MAC_B)
    assert old.miss_count == services.MISS_THRESHOLD
    assert (new.ip, new.miss_count) == ("10.60.1.10", 0)
    event = AssetEvent.objects.get(asset=old, kind=AssetEvent.Kind.DISAPPEARED)
    assert event.details["reason"] == "ip_reused"
    # активный актив с этим IP ровно один
    active_with_ip = Asset.objects.filter(ip="10.60.1.10", miss_count__lt=services.MISS_THRESHOLD)
    assert active_with_ip.count() == 1


def test_unknown_mac_is_enriched_not_reused(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.10")])
    result = services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])

    assert (result.new, result.disappeared) == (0, 0)
    asset = Asset.objects.get()
    assert asset.mac == MAC_A
    assert AssetEvent.objects.get(kind=AssetEvent.Kind.CHANGED).details == {
        "mac": {"from": "", "to": MAC_A}
    }


def test_ports_change_event(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A, ports=(22,))])
    result = services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A, ports=(22, 443))])

    asset = Asset.objects.get()
    assert asset.ports == [22, 443]
    assert result.ports_changed == 1  # счётчик в статистике скана
    assert AssetEvent.objects.get(kind=AssetEvent.Kind.PORTS_CHANGED).details == {
        "ports": {"from": [22], "to": [22, 443]}
    }


def test_empty_ports_do_not_wipe_known_data(segment: Segment) -> None:
    """ping-профиль не знает портов: пустой список — «нет данных», не «портов нет»."""
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A, ports=(22, 443))])
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])

    assert Asset.objects.get().ports == [22, 443]


def test_three_misses_mark_disappeared_once(segment: Segment) -> None:
    services.apply_observations(
        segment, [host("10.60.1.10", mac=MAC_A), host("10.60.1.11", mac=MAC_B)]
    )
    target = Asset.objects.get(ip="10.60.1.11")

    for expected_miss in (1, 2):
        result = services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
        assert result.disappeared == 0
        assert Asset.objects.get(pk=target.pk).miss_count == expected_miss

    result = services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
    target.refresh_from_db()
    assert (result.disappeared, target.miss_count) == (1, 3)
    assert AssetEvent.objects.filter(asset=target, kind=AssetEvent.Kind.DISAPPEARED).count() == 1

    # закрытый актив больше не «промахивается»
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
    target.refresh_from_db()
    assert target.miss_count == services.MISS_THRESHOLD


def test_reappearance_after_disappear_is_recorded(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.11", mac=MAC_B)])
    for _ in range(services.MISS_THRESHOLD):
        services.apply_observations(segment, [])
    assert Asset.objects.get().miss_count == services.MISS_THRESHOLD

    result = services.apply_observations(segment, [host("10.60.1.11", mac=MAC_B)])

    asset = Asset.objects.get()
    assert (result.reappeared, asset.miss_count) == (1, 0)
    assert AssetEvent.objects.filter(
        asset=asset, kind=AssetEvent.Kind.NEW, details__reason="reappeared"
    ).exists()


def test_asset_follows_mac_into_another_segment(segment: Segment) -> None:
    other = Segment.objects.create(
        site=segment.site, name="Сегмент-Другой", cidr="10.60.2.0/24", scan_enabled=False
    )
    services.apply_observations(segment, [host("10.60.1.10", mac=MAC_A)])
    services.apply_observations(other, [host("10.60.2.10", mac=MAC_A)])

    asset = Asset.objects.get()
    assert (asset.segment_id, asset.ip) == (other.pk, "10.60.2.10")
    assert AssetEvent.objects.get(kind=AssetEvent.Kind.CHANGED).details["segment"] == {
        "from": "Сегмент-Демо",
        "to": "Сегмент-Другой",
    }


def test_device_passport_is_filled_from_network_signals(segment: Segment) -> None:
    """Вендор (OUI), авто-роль и версии служб — из сетевых наблюдений (SDD §5.10)."""
    services.apply_observations(
        segment,
        [
            ObservedHost(
                ip="10.60.1.20",
                mac="08:55:31:aa:bb:cc",  # префикс MikroTik/Routerboard из OUI IEEE
                hostname="core-sw",
                ports=(8291,),
            ),
            ObservedHost(
                ip="10.60.1.21",
                mac=MAC_A,
                hostname="srv-demo",
                ports=(22, 443),
                services=(
                    {
                        "port": 443,
                        "service": "https",
                        "product": "nginx",
                        "version": "1.24.0",
                        "extrainfo": "",
                    },
                ),
            ),
        ],
    )

    mikrotik = Asset.objects.get(ip="10.60.1.20")
    assert "routerboard" in mikrotik.mac_vendor.lower()
    assert mikrotik.role_auto == "network"

    server = Asset.objects.get(ip="10.60.1.21")
    assert server.role_auto == "server"
    assert server.fingerprint["services"][0]["product"] == "nginx"


def test_passport_update_is_recorded_as_change(segment: Segment) -> None:
    services.apply_observations(segment, [host("10.60.1.30", mac=MAC_B)])
    services.apply_observations(segment, [host("10.60.1.30", mac=MAC_B, ports=(9100,))])

    asset = Asset.objects.get(ip="10.60.1.30")
    assert asset.role_auto == "printer"
    assert AssetEvent.objects.filter(
        kind=AssetEvent.Kind.CHANGED, details__role_auto__to="printer"
    ).exists()


# --- окно скана и расписание ----------------------------------------------------------


@freeze_time("2026-10-12 09:30:00+03:00")
def test_is_scan_allowed_respects_flag_and_window(segment: Segment) -> None:
    now = timezone.localtime()
    assert services.is_scan_allowed(segment, now) == (True, "")

    segment.scan_enabled = False
    assert services.is_scan_allowed(segment, now) == (False, "scan_disabled")


def test_manual_scan_ignores_window_but_not_the_switch(segment: Segment) -> None:
    """Кнопка «просканировать сейчас» работает вне окна, но выключатель скана уважает."""
    now = timezone.localtime()
    tomorrow = (now.weekday() + 1) % 7
    segment.scan_window = {"days": [tomorrow], "start": "08:00", "end": "14:00"}

    assert services.is_scan_allowed(segment, now) == (False, "outside_window")
    assert services.is_scan_allowed(segment, now, manual=True) == (True, "")

    segment.scan_enabled = False
    assert services.is_scan_allowed(segment, now, manual=True) == (False, "scan_disabled")

    segment.scan_enabled = True
    segment.scan_window = {"days": [1], "start": "09:00", "end": "18:00"}  # вторник днём
    assert services.is_scan_allowed(segment, now) == (False, "outside_window")

    segment.scan_window = {"days": [7], "start": "09:00", "end": "18:00"}  # битое окно
    assert services.is_scan_allowed(segment, now) == (False, "bad_window")


@freeze_time("2026-10-12 09:30:00+03:00")
def test_due_segments_selects_only_enabled_due_in_window(segment: Segment) -> None:
    now = timezone.localtime()
    assert services.due_segments(now) == [segment]

    segment.last_scan_at = timezone.now()
    segment.save(update_fields=["last_scan_at"])
    assert services.due_segments(now) == []

    segment.last_scan_at = timezone.now() - timedelta(hours=services.SCAN_INTERVAL_HOURS + 1)
    segment.save(update_fields=["last_scan_at"])
    assert services.due_segments(now) == [segment]

    segment.scan_enabled = False
    segment.save(update_fields=["scan_enabled"])
    assert services.due_segments(now) == []


@freeze_time("2026-10-12 16:00:00+03:00")
def test_due_segments_skips_closed_window(segment: Segment) -> None:
    assert services.due_segments(timezone.localtime()) == []
