"""Задачи обязательств (beat: утро буднего дня)."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.obligations.services import daily_run


@shared_task
def daily_obligations() -> dict:
    """Материализация инстансов, статусы, напоминания 30/7/1, эскалации."""
    return daily_run(timezone.localtime())
