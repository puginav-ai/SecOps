"""Задачи discovery: плановый обход сегментов и скан одного сегмента (SDD §5.2)."""

from __future__ import annotations

import logging
from dataclasses import asdict

from celery import shared_task
from django.utils import timezone

from apps.discovery.models import RouterDevice, ScanRun
from apps.discovery.scanner import collect_observations, router_sources
from apps.discovery.services import apply_observations, due_segments, is_scan_allowed
from apps.registry.models import Segment
from collector.mikrotik import fetch_router_data, normalized_addresses

logger = logging.getLogger(__name__)


@shared_task
def refresh_router_inventory() -> int:
    """Инвентарь роутеров для карты: имя и адреса интерфейсов (RouterOS API, чтение)."""
    updated = 0
    for host, user, password, use_ssl in router_sources():
        if not host:
            continue
        try:
            data = fetch_router_data(host, user, password, use_ssl=use_ssl)
        except Exception:
            logger.exception("router inventory failed", extra={"host": host})
            continue
        RouterDevice.objects.update_or_create(
            host=host,
            defaults={
                "name": data.identity or host,
                "addresses": normalized_addresses(data.addresses),
                "last_seen_at": timezone.now(),
            },
        )
        updated += 1
    return updated


@shared_task
def scan_due_segments() -> int:
    """Ставит в очередь сегменты, которым пора на обход. Возвращает число поставленных."""
    now = timezone.localtime()
    segments = due_segments(now)
    for segment in segments:
        scan_segment.apply_async(args=[segment.pk, ScanRun.Trigger.SCHEDULE.value], queue="scan")
    return len(segments)


@shared_task
def scan_segment(segment_id: int, triggered_by: str = ScanRun.Trigger.SCHEDULE.value) -> dict:
    """Скан одного сегмента: проверка окна, nmap, upsert активов, журнал запуска."""
    segment = Segment.objects.get(pk=segment_id)
    allowed, reason = is_scan_allowed(
        segment, timezone.localtime(), manual=triggered_by == ScanRun.Trigger.MANUAL.value
    )
    if not allowed:
        logger.info("scan refused", extra={"segment_id": segment.pk, "reason": reason})
        return {"status": "refused", "reason": reason}

    run = ScanRun.objects.create(segment=segment, triggered_by=triggered_by)
    try:
        observations = collect_observations(segment)
    except Exception as exc:  # журнал не должен оставаться в running
        run.status = ScanRun.Status.FAILED
        run.stats = {"error": str(exc)}
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "stats", "finished_at"])
        raise

    result = apply_observations(segment, observations)

    now = timezone.now()
    run.status = ScanRun.Status.OK
    run.stats = asdict(result)
    run.finished_at = now
    run.save(update_fields=["status", "stats", "finished_at"])
    segment.last_scan_at = now
    segment.save(update_fields=["last_scan_at"])

    return {"status": "ok", **asdict(result)}
