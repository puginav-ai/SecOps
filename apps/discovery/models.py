"""Discovery: журнал запусков сканов."""

from __future__ import annotations

from django.db import models

from apps.registry.models import Segment


class ScanRun(models.Model):
    """Журнал запусков discovery (SDD §3.1); бюджет и статусы — §5.2."""

    class Status(models.TextChoices):
        RUNNING = "running", "выполняется"
        OK = "ok", "успешно"
        FAILED = "failed", "ошибка"

    class Trigger(models.TextChoices):
        SCHEDULE = "schedule", "по расписанию"
        MANUAL = "manual", "вручную"

    segment = models.ForeignKey(
        Segment,
        verbose_name="сегмент",
        on_delete=models.PROTECT,
        related_name="scan_runs",
    )
    started_at = models.DateTimeField("начало", auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField("окончание", null=True, blank=True)
    status = models.CharField(
        "статус", max_length=10, choices=Status.choices, default=Status.RUNNING
    )
    stats = models.JSONField("статистика", default=dict, blank=True)
    triggered_by = models.CharField(
        "инициатор", max_length=10, choices=Trigger.choices, default=Trigger.SCHEDULE
    )

    class Meta:
        verbose_name = "Запуск скана"
        verbose_name_plural = "Журнал сканов"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.started_at:%Y-%m-%d %H:%M} {self.segment_id} {self.status}"
