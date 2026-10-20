"""Операции discovery: upsert активов, окно скана, расписание (SDD §5.2).

MAC-first идентичность: устройство «переезжает» вместе с MAC; занятый другим MAC IP —
новый актив, старый закрывается (disappeared/reason=ip_reused). Анти-мигание: пропажа
фиксируется после MISS_THRESHOLD промахов подряд.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.registry.models import Asset, AssetEvent, Segment
from collector.classify import (
    better_os_family,
    classify_role,
    derive_os_family,
    distro_from_services,
)
from collector.nmap import ObservedHost
from collector.oui import vendor_for_mac
from collector.window import in_scan_window

logger = logging.getLogger(__name__)

MISS_THRESHOLD = 3  # «пропал» — после 3 промахов подряд (SDD §5.2)
SCAN_INTERVAL_HOURS = 24  # плановый обход сегмента — раз в сутки (SDD §5.2)


@dataclass
class ApplyResult:
    """Итог применения наблюдений: счётчики для scan_runs.stats."""

    seen: int = 0
    new: int = 0
    changed: int = 0
    ports_changed: int = 0
    disappeared: int = 0
    reappeared: int = 0


def is_scan_allowed(segment: Segment, now: datetime, *, manual: bool = False) -> tuple[bool, str]:
    """Разрешён ли скан сегмента сейчас. Причина отказа: scan_disabled|outside_window|bad_window.

    Ручной запуск (кнопка «просканировать сейчас») игнорирует окно — это осознанное действие
    администратора; выключатель скана (`scan_enabled`) уважается всегда (SDD §5.2).
    """
    if not segment.scan_enabled:
        return False, "scan_disabled"
    if manual:
        return True, ""
    try:
        allowed = in_scan_window(segment.scan_window, now)
    except ValueError:
        logger.warning("bad scan window", extra={"segment_id": segment.pk})
        return False, "bad_window"
    return (True, "") if allowed else (False, "outside_window")


def due_segments(now: datetime) -> list[Segment]:
    """Сегменты к плановому обходу: скан включён, интервал прошёл, окно открыто."""
    threshold = now - timedelta(hours=SCAN_INTERVAL_HOURS)
    candidates = Segment.objects.filter(scan_enabled=True).filter(
        Q(last_scan_at__isnull=True) | Q(last_scan_at__lt=threshold)
    )
    return [segment for segment in candidates if is_scan_allowed(segment, now)[0]]


def apply_observations(segment: Segment, observations: Sequence[ObservedHost]) -> ApplyResult:
    """Upsert наблюдений скана в активы сегмента: создать/обновить/закрыть + события дрейфа."""
    now = timezone.now()
    result = ApplyResult()
    seen_ids: set[int] = set()

    for observed in observations:
        result.seen += 1
        mac = observed.mac.lower() if observed.mac else None

        asset: Asset | None = None
        if mac:
            asset = Asset.objects.filter(mac=mac).order_by("pk").first()

        if asset is None:
            by_ip = (
                Asset.objects.filter(ip=observed.ip, miss_count__lt=MISS_THRESHOLD)
                .order_by("pk")
                .first()
            )
            if by_ip is not None and mac and by_ip.mac and by_ip.mac != mac:
                # IP занят другим устройством: прежний актив закрываем (SDD §5.2)
                _mark_disappeared(by_ip, {"reason": "ip_reused", "mac": by_ip.mac})
                result.disappeared += 1
            else:
                asset = by_ip

        if asset is None:
            vendor = vendor_for_mac(mac or "")
            asset = Asset.objects.create(
                ip=observed.ip,
                mac=mac or "",
                mac_vendor=vendor,
                hostname=observed.hostname,
                os_name=observed.os_name,
                os_family=(
                    distro_from_services(observed.services)
                    or derive_os_family(observed.ports, vendor)
                ),
                site=segment.site,
                segment=segment,
                discovery_source=observed.source,
                ports=list(observed.ports),
                role_auto=classify_role(
                    observed.ports, vendor, observed.hostname, observed.os_name
                ),
                fingerprint={"services": list(observed.services)} if observed.services else {},
                software=software_label(observed),
                last_seen_at=now,
            )
            AssetEvent.objects.create(asset=asset, kind=AssetEvent.Kind.NEW)
            result.new += 1
            seen_ids.add(asset.pk)
            continue

        seen_ids.add(asset.pk)
        reopened = asset.miss_count >= MISS_THRESHOLD
        changes, ports_changed = _update_asset(asset, observed, segment, mac, now)
        if ports_changed:
            result.ports_changed += 1
        if changes:
            AssetEvent.objects.create(asset=asset, kind=AssetEvent.Kind.CHANGED, details=changes)
            result.changed += 1
        if reopened:
            AssetEvent.objects.create(
                asset=asset, kind=AssetEvent.Kind.NEW, details={"reason": "reappeared"}
            )
            result.reappeared += 1

    # промахи: активы сегмента, не увиденные в этом скане
    absent = Asset.objects.filter(segment=segment, miss_count__lt=MISS_THRESHOLD).exclude(
        pk__in=seen_ids
    )
    for asset in absent:
        asset.miss_count += 1
        if asset.miss_count >= MISS_THRESHOLD:
            _mark_disappeared(asset, {"reason": "no_response"})
            result.disappeared += 1
        else:
            asset.save(update_fields=["miss_count"])

    return result


def _update_asset(
    asset: Asset, observed: ObservedHost, segment: Segment, mac: str | None, now: datetime
) -> tuple[dict, bool]:
    """Обновляет поля актива; возвращает (изменения для changed, сменились ли порты)."""
    changes: dict = {}
    for field, old, new in (
        ("ip", asset.ip, observed.ip),
        ("mac", asset.mac, mac),
        ("hostname", asset.hostname, observed.hostname),
        ("os_name", asset.os_name, observed.os_name),
    ):
        if new and old != new:
            changes[field] = {"from": old, "to": new}

    if asset.segment_id != segment.pk:
        changes["segment"] = {
            "from": asset.segment.name if asset.segment else None,
            "to": segment.name,
        }

    ports = list(observed.ports)
    # пустой список портов = «нет данных порт-скана», а не «портов нет» (shortcut)
    ports_changed = bool(ports) and asset.ports != ports
    if ports_changed:
        AssetEvent.objects.create(
            asset=asset,
            kind=AssetEvent.Kind.PORTS_CHANGED,
            details={"ports": {"from": asset.ports, "to": ports}},
        )
        asset.ports = ports

    # Паспорт устройства (SDD §5.10): вендор по OUI, роль по правилам, версии служб.
    effective_mac = mac or asset.mac
    vendor = vendor_for_mac(effective_mac or "")
    if vendor and vendor != asset.mac_vendor:
        changes["mac_vendor"] = {"from": asset.mac_vendor, "to": vendor}

    effective_hostname = observed.hostname or asset.hostname
    role_auto = classify_role(
        ports or asset.ports,
        vendor or asset.mac_vendor,
        effective_hostname,
        observed.os_name or asset.os_name,
    )
    # Пустая классификация очищает устаревшую авто-роль, если по хосту есть порты:
    # иначе «сервер» из старых правил (SSH/веб) остаётся навсегда. Без портов — не трогаем.
    if role_auto != asset.role_auto and (role_auto or asset.ports):
        changes["role_auto"] = {"from": asset.role_auto, "to": role_auto}
        asset.role_auto = role_auto

    services = [dict(item) for item in observed.services]
    if services and services != (asset.fingerprint or {}).get("services", []):
        changes["services"] = {
            "from": (asset.fingerprint or {}).get("services", []),
            "to": services,
        }

    asset.ip = observed.ip
    asset.mac = mac or asset.mac
    asset.mac_vendor = vendor or asset.mac_vendor
    if services:
        asset.fingerprint = {**(asset.fingerprint or {}), "services": services}
        asset.software = software_label(observed)
    asset.hostname = observed.hostname or asset.hostname
    asset.os_name = observed.os_name or asset.os_name
    # ОС для поиска: точная из SMB/RDP или SSH-баннера; иначе подсказка по портам/вендору
    if not asset.os_name:
        os_family = better_os_family(
            asset.os_family,
            distro_from_services(services)
            or derive_os_family(ports or asset.ports, vendor or asset.mac_vendor),
        )
        if os_family and os_family != asset.os_family:
            changes["os_family"] = {"from": asset.os_family, "to": os_family}
            asset.os_family = os_family
    asset.site = segment.site
    asset.segment = segment
    asset.last_seen_at = now
    asset.miss_count = 0
    asset.save()
    return changes, ports_changed


def software_label(observed: ObservedHost) -> str:
    """Человекочитаемая строка «продукт версия; …» из версий nmap -sV (для фильтра и выгрузки)."""
    labels = []
    for item in observed.services:
        label = " ".join(
            part for part in (item.get("product", ""), item.get("version", "")) if part
        )
        labels.append(label or item.get("service", ""))
    return "; ".join(sorted(filter(None, labels)))[:500]


def _mark_disappeared(asset: Asset, details: dict) -> None:
    asset.miss_count = MISS_THRESHOLD
    asset.save(update_fields=["miss_count"])
    AssetEvent.objects.create(asset=asset, kind=AssetEvent.Kind.DISAPPEARED, details=details)
