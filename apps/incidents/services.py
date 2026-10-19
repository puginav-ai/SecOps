"""Сервисы инцидентов: стадии из правил, таймеры, закрытие (SDD §3.6, §5.7)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.access import ROLE_TITLES
from apps.incidents.models import Incident, IncidentNotification, IncidentNotificationRule
from apps.notifications.services import notify_user


def rule_applies(rule: IncidentNotificationRule, incident: Incident) -> bool:
    """Условие применимости (applies_if): напр. {"kii_scope": "yes"} только для КИИ-контуров."""
    condition = rule.applies_if or {}
    if not condition:
        return True
    system = incident.system
    if "kii_scope" in condition:
        return bool(system and system.kii_scope == condition["kii_scope"])
    if "has_pdn" in condition:
        return bool(system and system.has_pdn == condition["has_pdn"])
    # Неизвестное условие — правило не применяем (безопасное поведение)
    return False


def stage_message(stage: IncidentNotification) -> str:
    local = timezone.localtime(stage.deadline_at)
    return (
        f"Инцидент #{stage.incident_id}: стадия «{stage.stage_code}» — "
        f"{stage.rule.template_code} (до {local:%d.%m %H:%M})"
    )


def notify_stage(stage: IncidentNotification) -> int:
    """Уведомляет получателей стадии (по коду роли); внешние получатели — только таймер."""
    rule = stage.rule
    sent = 0
    if rule.target in ROLE_TITLES:
        users = get_user_model().objects.filter(groups__name=rule.target, is_active=True)
        for user in users:
            sent += notify_user(
                user,
                "incident_stage",
                stage_message(stage),
                incident=stage.incident,
                dedup_suffix=f"stage{stage.pk}",
            )
    return sent


def create_incident(
    *,
    kind: str,
    detected_at,
    system=None,
    severity: str,
    description: str,
    user=None,
) -> Incident:
    """Регистрирует инцидент и разворачивает стадии из справочника правил (таймеры)."""
    incident = Incident.objects.create(
        kind=kind,
        detected_at=detected_at,
        system=system,
        severity=severity,
        description=description,
        created_by=user,
    )
    for rule in IncidentNotificationRule.objects.filter(kind__in=[kind, ""]):
        if not rule_applies(rule, incident):
            continue
        stage = IncidentNotification.objects.create(
            incident=incident,
            rule=rule,
            stage_code=rule.stage_code,
            deadline_at=detected_at + timedelta(minutes=rule.offset_minutes),
        )
        notify_stage(stage)
    return incident


def mark_stage_sent(stage: IncidentNotification, *, evidence, channel: str, now=None) -> None:
    """Закрытие стадии: отправка подтверждается evidence (SDD §3.6)."""
    if stage.sent_at is not None:
        raise ValidationError("Стадия уже закрыта")
    if evidence is None:
        raise ValidationError("Закрытие стадии требует evidence отправки")
    stage.sent_at = now or timezone.now()
    stage.evidence = evidence
    stage.channel = channel
    stage.status = IncidentNotification.Status.SENT
    stage.save(update_fields=["sent_at", "evidence", "channel", "status"])


def start_investigation(incident: Incident) -> None:
    if incident.status == Incident.Status.OPEN:
        incident.status = Incident.Status.INVESTIGATING
        incident.save(update_fields=["status"])


def close_incident(incident: Incident) -> None:
    """Закрытие инцидента: только при отсутствии открытых стадий (SDD §5.7)."""
    if incident.status == Incident.Status.CLOSED:
        raise ValidationError("Инцидент уже закрыт")
    if incident.stages.filter(sent_at__isnull=True).exists():
        raise ValidationError("Нельзя закрыть инцидент: есть незакрытые стадии уведомлений")
    incident.status = Incident.Status.CLOSED
    incident.closed_at = timezone.now()
    incident.save(update_fields=["status", "closed_at"])


def overdue_stages(now=None):
    """Стадии с прошедшим сроком и без отправки — для дашборда и эскалаций."""
    now = now or timezone.now()
    return (
        IncidentNotification.objects.filter(
            sent_at__isnull=True,
            deadline_at__lt=now,
            incident__status__in=[Incident.Status.OPEN, Incident.Status.INVESTIGATING],
        )
        .select_related("incident", "rule")
        .order_by("deadline_at")
    )


def escalate_overdue(now=None) -> int:
    """Ежедневная эскалация просроченных стадий ИБ-админам (дедуп — раз в день)."""
    now = now or timezone.now()
    sent = 0
    day = timezone.localtime(now).date().isoformat()
    admins = get_user_model().objects.filter(groups__name="ib_admin", is_active=True)
    for stage in overdue_stages(now):
        message = f"ПРОСРОЧЕНО: {stage_message(stage)}"
        for user in admins:
            sent += notify_user(
                user,
                "incident_overdue",
                message,
                incident=stage.incident,
                dedup_suffix=f"overdue{stage.pk}-{day}",
            )
    return sent
