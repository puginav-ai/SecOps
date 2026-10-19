"""Задачи инцидентов: ежедневная эскалация просроченных стадий."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.incidents.services import escalate_overdue


@shared_task
def escalate_overdue_stages() -> int:
    return escalate_overdue(timezone.now())
