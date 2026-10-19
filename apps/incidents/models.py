"""Инциденты: реестр, справочник правил стадий, таймеры, evidence отправки (SDD §3.6)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Incident(models.Model):
    class Kind(models.TextChoices):
        KII = "kii", "КИИ"
        PDN = "pdn", "ПДн"
        MEDICAL = "medical", "Медицина"
        INFRA = "infra", "Инфраструктура"
        OTHER = "other", "Прочее"

    class Severity(models.TextChoices):
        LOW = "low", "низкая"
        MEDIUM = "medium", "средняя"
        HIGH = "high", "высокая"

    class Status(models.TextChoices):
        OPEN = "open", "открыт"
        INVESTIGATING = "investigating", "разбор"
        CLOSED = "closed", "закрыт"

    kind = models.CharField("вид", max_length=10, choices=Kind.choices, default=Kind.OTHER)
    detected_at = models.DateTimeField("обнаружен", db_index=True)
    system = models.ForeignKey(
        "registry.System",
        verbose_name="ИС",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    severity = models.CharField(
        "серьёзность", max_length=10, choices=Severity.choices, default=Severity.MEDIUM
    )
    description = models.TextField("описание")
    status = models.CharField("статус", max_length=15, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField("закрыт", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="зарегистрировал",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incidents",
    )
    created_at = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        verbose_name = "Инцидент"
        verbose_name_plural = "Инциденты"
        ordering = ["-detected_at"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.get_kind_display()} ({self.get_severity_display()})"


class IncidentNotificationRule(models.Model):
    """Правило стадии уведомлений: таймер = detected_at + offset (SDD §3.6).

    `applies_if` — условие применимости, например {"kii_scope": "yes"} для стадии «1 час».
    `target` — код роли (ib_admin, ib_officer, it_ops) или внешний получатель (regulator).
    `template_code` — текст-шаблон уведомления (MVP: короткая строка-тема).
    """

    kind = models.CharField(
        "вид инцидента", max_length=10, choices=Incident.Kind.choices, blank=True, default=""
    )
    stage_code = models.CharField("код стадии", max_length=30)
    offset_minutes = models.PositiveIntegerField("срок, минут от обнаружения")
    target = models.CharField("получатель", max_length=50)
    template_code = models.CharField("шаблон уведомления", max_length=200)
    applies_if = models.JSONField("условие применимости", default=dict, blank=True)
    note = models.CharField("примечание", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "Правило стадии"
        verbose_name_plural = "Справочник правил стадий"
        ordering = ["offset_minutes", "stage_code"]

    def __str__(self) -> str:
        return f"{self.stage_code} +{self.offset_minutes} мин"


class IncidentNotification(models.Model):
    """Стадия инцидента (таймер): закрывается отправкой с evidence (SDD §3.6)."""

    class Status(models.TextChoices):
        PENDING = "pending", "ожидает"
        SENT = "sent", "отправлено"

    class Channel(models.TextChoices):
        EMAIL = "email", "email"
        LETTER = "letter", "письмо"
        PHONE = "phone", "телефон"
        OTHER = "other", "прочее"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="stages")
    rule = models.ForeignKey(
        IncidentNotificationRule, on_delete=models.PROTECT, related_name="stages"
    )
    stage_code = models.CharField("стадия", max_length=30)
    deadline_at = models.DateTimeField("срок", db_index=True)
    sent_at = models.DateTimeField("отправлено", null=True, blank=True)
    status = models.CharField(
        "статус", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    channel = models.CharField(
        "канал отправки", max_length=10, choices=Channel.choices, blank=True, default=""
    )
    evidence = models.ForeignKey(
        "evidence.EvidenceObject",
        verbose_name="evidence отправки",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_stages",
    )

    class Meta:
        verbose_name = "Стадия инцидента"
        verbose_name_plural = "Стадии инцидентов"
        constraints = [
            models.UniqueConstraint(fields=["incident", "rule"], name="uniq_incident_stage")
        ]
        ordering = ["deadline_at"]

    def __str__(self) -> str:
        return f"{self.incident} · {self.stage_code}"

    @property
    def is_overdue(self) -> bool:
        """Просрочена: не отправлена, а срок прошёл."""
        return self.sent_at is None and self.deadline_at < timezone.now()

    @property
    def seconds_left(self) -> float:
        return (self.deadline_at - timezone.now()).total_seconds()
