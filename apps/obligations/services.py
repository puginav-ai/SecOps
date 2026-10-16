"""Сервисы обязательств: материализация, статусы, напоминания, эскалации (SDD §3.5, §5.5)."""

from __future__ import annotations

import logging

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.notifications.services import notify_person, notify_user
from apps.obligations.models import ObligationInstance, ObligationTemplate
from apps.registry.models import Person

logger = logging.getLogger(__name__)

HORIZON_MONTHS = 18  # материализация вперёд (SDD §3.5)
DUE_SOON_DAYS = 30  # «скоро срок» = в пределах окна напоминаний


def materialize(template: ObligationTemplate, now, horizon_months: int = HORIZON_MONTHS) -> int:
    """Создаёт инстансы шаблона вперёд по горизонту. Идемпотентно. Возвращает число новых."""
    if not template.recurrence_rule:
        if template.instances.exists():
            return 0
        ObligationInstance.objects.create(template=template, due_at=now)
        return 1

    last = template.instances.order_by("-due_at").first()
    start = last.due_at if last else now
    rule = rrulestr(template.recurrence_rule, dtstart=start)
    horizon = now + relativedelta(months=horizon_months)
    created = 0
    for due in rule:
        if due > horizon:
            break
        _, was_created = ObligationInstance.objects.get_or_create(
            template=template, due_at=due, related_entity_id=None
        )
        created += int(was_created)
    return created


def refresh_statuses(now) -> int:
    """planned → due_soon/overdue по сроку. Возвращает число изменений."""
    changed = 0
    active = ObligationInstance.objects.filter(
        status__in=[ObligationInstance.Status.PLANNED, ObligationInstance.Status.DUE_SOON]
    )
    for instance in active:
        if instance.due_at < now:
            new_status = ObligationInstance.Status.OVERDUE
        elif (instance.due_at - now).days <= DUE_SOON_DAYS:
            new_status = ObligationInstance.Status.DUE_SOON
        else:
            new_status = instance.status
        if new_status != instance.status:
            instance.status = new_status
            instance.save(update_fields=["status"])
            changed += 1
    return changed


def send_reminders(now) -> int:
    """Напоминания владельцам ровно за lead_days (дедупликация через уведомления)."""
    today = timezone.localtime(now).date()
    sent = 0
    active = ObligationInstance.objects.filter(
        status__in=[
            ObligationInstance.Status.PLANNED,
            ObligationInstance.Status.DUE_SOON,
            ObligationInstance.Status.OVERDUE,
        ],
        owner_person__isnull=False,
    ).select_related("template", "owner_person")
    for instance in active:
        due_date = timezone.localtime(instance.due_at).date()
        days_left = (due_date - today).days
        for lead in instance.template.lead_days or []:
            if days_left == lead:
                sent += notify_person(
                    instance.owner_person,
                    "obligation_reminder",
                    f"Напоминание: «{instance.template.name}» — через {lead} дн. "
                    f"(срок {due_date:%d.%m.%Y})",
                    instance=instance,
                    dedup_suffix=f"lead{lead}",
                )
    return sent


def run_escalations(now) -> int:
    """Эскалации просроченных по шагам политики; уровень фиксируется в инстансе."""
    sent = 0
    overdue = ObligationInstance.objects.filter(
        status=ObligationInstance.Status.OVERDUE
    ).select_related("template")
    for instance in overdue:
        days_over = (now - instance.due_at).days
        for step in sorted(
            instance.template.escalation_policy or [], key=lambda s: s.get("step", 0)
        ):
            step_number = int(step.get("step", 0))
            if (
                days_over < int(step.get("after_days", 0))
                or instance.escalation_level >= step_number
            ):
                continue
            message = (
                f"Просрочено: «{instance.template.name}» (срок "
                f"{timezone.localtime(instance.due_at):%d.%m.%Y}, шаг эскалации {step_number})"
            )
            for recipient in step.get("recipients", []):
                if "person_id" in recipient:
                    person = Person.objects.filter(pk=recipient["person_id"]).first()
                    if person is not None:
                        sent += notify_person(
                            person,
                            "obligation_escalation",
                            message,
                            instance=instance,
                            dedup_suffix=f"step{step_number}",
                        )
                elif "role" in recipient:
                    users = get_user_model().objects.filter(groups__name=recipient["role"])
                    for user in users:
                        sent += notify_user(
                            user,
                            "obligation_escalation",
                            message,
                            instance=instance,
                            dedup_suffix=f"step{step_number}",
                        )
            instance.escalation_level = step_number
            instance.save(update_fields=["escalation_level"])
    return sent


def daily_run(now) -> dict:
    """Ежедневный цикл: материализация → статусы → напоминания → эскалации."""
    created = 0
    for template in ObligationTemplate.objects.all():
        created += materialize(template, now)
    statuses = refresh_statuses(now)
    reminders = send_reminders(now)
    escalations = run_escalations(now)
    logger.info(
        "obligations daily run",
        extra={
            "instances_created": created,
            "statuses": statuses,
            "reminders": reminders,
            "escalations": escalations,
        },
    )
    return {
        "created": created,
        "statuses": statuses,
        "reminders": reminders,
        "escalations": escalations,
    }
