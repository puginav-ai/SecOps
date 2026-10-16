"""Обязательства: шаблоны (RRULE) и инстансы, напоминания и эскалации (SDD §3.5, неделя 6)."""

from __future__ import annotations

from django.db import models

from apps.core.access import ROLE_TITLES


def default_lead_days() -> list[int]:
    return [30, 7, 1]


class ObligationTemplate(models.Model):
    """Шаблон обязательства: периодичность (RRULE) или разовое событие."""

    class Kind(models.TextChoices):
        KZI = "kzi", "КЗИ"
        PZI = "pzi", "ПЗИ"
        REPORT = "report", "Отчётность"
        CONTRACT = "contract", "Договоры/assurance"
        FSTEC = "fstec_reply", "Контроль ответа ФСТЭК"
        BACKUP = "backup", "Проверка бэкапов"
        TELEMEDICINE = "telemedicine", "Телемедицина"
        UPDATE = "update", "Обновления"
        OTHER = "other", "Прочее"

    kind = models.CharField("вид", max_length=20, choices=Kind.choices, default=Kind.OTHER)
    name = models.CharField("название", max_length=200)
    recurrence_rule = models.CharField(
        "RRULE", max_length=200, blank=True, default="", help_text="пусто = разовое/по событию"
    )
    lead_days = models.JSONField("напоминать за N дней", default=default_lead_days, blank=True)
    escalation_policy = models.JSONField(
        "политика эскалации",
        default=list,
        blank=True,
        help_text='[{"step":1,"after_days":3,"recipients":[{"role":"ib_admin"}]}]',
    )
    applies_to = models.JSONField(
        "применимо к", default=list, blank=True, help_text='например ["lis","pacs"]'
    )
    requires_closing_evidence = models.BooleanField("закрытие с evidence", default=False)
    owner_role = models.CharField(
        "роль владельца",
        max_length=20,
        blank=True,
        default="",
        choices=[(code, title) for code, title in ROLE_TITLES.items()],
    )
    created_at = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        verbose_name = "Шаблон обязательства"
        verbose_name_plural = "Шаблоны обязательств"
        ordering = ["kind", "name"]

    def __str__(self) -> str:
        return self.name


class ObligationInstance(models.Model):
    """Инстанс обязательства со сроком; материализуется beat'ом на 12–18 мес. вперёд."""

    class Status(models.TextChoices):
        PLANNED = "planned", "запланировано"
        DUE_SOON = "due_soon", "скоро срок"
        OVERDUE = "overdue", "просрочено"
        DONE = "done", "выполнено"
        CANCELLED = "cancelled", "отменено"

    template = models.ForeignKey(
        ObligationTemplate,
        verbose_name="шаблон",
        on_delete=models.PROTECT,
        related_name="instances",
    )
    due_at = models.DateTimeField("срок", db_index=True)
    status = models.CharField(
        "статус", max_length=10, choices=Status.choices, default=Status.PLANNED
    )
    owner_person = models.ForeignKey(
        "registry.Person",
        verbose_name="ответственный",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="obligations",
    )
    related_entity_type = models.CharField(
        "тип связанного объекта", max_length=50, blank=True, default=""
    )
    related_entity_id = models.BigIntegerField("id связанного объекта", null=True, blank=True)
    escalation_level = models.PositiveSmallIntegerField("уровень эскалации", default=0)
    closure_evidence = models.ForeignKey(
        "evidence.EvidenceObject",
        verbose_name="evidence закрытия",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="closed_obligations",
    )
    closed_at = models.DateTimeField("закрыто", null=True, blank=True)

    class Meta:
        verbose_name = "Обязательство"
        verbose_name_plural = "Обязательства (инстансы)"
        constraints = [
            models.UniqueConstraint(
                fields=["template", "due_at", "related_entity_id"],
                name="uniq_obligation_instance",
                nulls_distinct=False,
            )
        ]
        ordering = ["due_at"]

    def __str__(self) -> str:
        return f"{self.template.name} @ {self.due_at:%d.%m.%Y}"

    @property
    def is_active(self) -> bool:
        return self.status in {self.Status.PLANNED, self.Status.DUE_SOON, self.Status.OVERDUE}
