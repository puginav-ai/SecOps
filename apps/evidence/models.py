"""Evidence: файлы, письма, связи (SDD §3.3, неделя 5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone

# Известные типы сущностей для связей «evidence → объект»
ENTITY_TYPE_CHOICES = [
    ("test_run", "проверка контроля"),
    ("obligation_instance", "обязательство"),
    ("system", "ИС"),
    ("incident", "инцидент"),
]


def evidence_path(instance: EvidenceObject, filename: str) -> str:
    """Ключ в хранилище: evidence/<год>/<месяц>/<имя файла>."""
    today = timezone.localdate()
    return f"evidence/{today:%Y/%m}/{filename}"


class EvidenceObject(models.Model):
    class Kind(models.TextChoices):
        LETTER = "letter", "письмо"
        ACT = "act", "акт"
        CONTRACT = "contract", "договор"
        EXPORT = "export", "выгрузка"
        REPORT = "report", "отчёт"
        SCREENSHOT = "screenshot", "скриншот"
        SCAN = "scan", "скан"
        OTHER = "other", "прочее"

    class Confidentiality(models.TextChoices):
        PUBLIC = "public", "общий"
        INTERNAL = "internal", "внутренний"
        RESTRICTED = "restricted", "ограниченный"

    class LetterDirection(models.TextChoices):
        IN = "in", "входящее"
        OUT = "out", "исходящее"

    class ReplyStatus(models.TextChoices):
        WAITING = "waiting", "ждём ответ"
        ANSWERED = "answered", "ответ получен"
        OVERDUE = "overdue", "просрочен"

    title = models.CharField("название", max_length=300)
    kind = models.CharField("вид", max_length=20, choices=Kind.choices, default=Kind.OTHER)
    file = models.FileField("файл", upload_to=evidence_path)
    filename = models.CharField("имя файла", max_length=255, blank=True, default="")
    mime = models.CharField("MIME", max_length=100, blank=True, default="")
    size = models.BigIntegerField("размер, байт", default=0)
    sha256 = models.CharField("sha256", max_length=64, blank=True, default="")
    issued_at = models.DateField("дата документа", null=True, blank=True)
    valid_until = models.DateField("действует до", null=True, blank=True)
    confidentiality = models.CharField(
        "конфиденциальность",
        max_length=10,
        choices=Confidentiality.choices,
        default=Confidentiality.INTERNAL,
    )
    # Поля писем — только для kind=letter (индексируются, SDD §3.3)
    letter_direction = models.CharField(
        "направление письма", max_length=3, choices=LetterDirection.choices, blank=True, default=""
    )
    letter_number = models.CharField("номер письма", max_length=100, blank=True, default="")
    letter_date = models.DateField("дата письма", null=True, blank=True)
    correspondent = models.CharField("корреспондент", max_length=200, blank=True, default="")
    reply_due_at = models.DateField("ответ к дате", null=True, blank=True)
    reply_status = models.CharField(
        "статус ответа", max_length=10, choices=ReplyStatus.choices, blank=True, default=""
    )
    metadata = models.JSONField("метаданные", default=dict, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="загрузил",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_uploads",
    )
    created_at = models.DateTimeField("загружено", auto_now_add=True)

    class Meta:
        verbose_name = "Evidence"
        verbose_name_plural = "Evidence (доказательства)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kind", "-created_at"]),
            models.Index(fields=["valid_until"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:
        if self.file and not self.sha256:
            self.sha256 = self.compute_sha256()
            try:
                self.file.seek(0)
            except (AttributeError, OSError):
                pass
        if self.file:
            self.size = self.file.size or self.size
            if not self.filename:
                self.filename = Path(self.file.name).name
        super().save(*args, **kwargs)

    def compute_sha256(self) -> str:
        digest = hashlib.sha256()
        for chunk in self.file.chunks():
            digest.update(chunk)
        return digest.hexdigest()


class EvidenceLink(models.Model):
    """Связь evidence с объектом (SDD §3.3); пара с ролью уникальна."""

    class Role(models.TextChoices):
        PROOF = "proof", "доказательство"
        SOURCE = "source", "источник"
        ATTACHMENT = "attachment", "приложение"

    evidence = models.ForeignKey(
        EvidenceObject, verbose_name="evidence", on_delete=models.CASCADE, related_name="links"
    )
    entity_type = models.CharField("тип объекта", max_length=50, choices=ENTITY_TYPE_CHOICES)
    entity_id = models.BigIntegerField("id объекта")
    role = models.CharField("роль", max_length=10, choices=Role.choices, default=Role.PROOF)

    class Meta:
        verbose_name = "Связь evidence"
        verbose_name_plural = "Связи evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["evidence", "entity_type", "entity_id", "role"],
                name="uniq_evidence_link",
            )
        ]
        ordering = ["entity_type", "entity_id"]

    def __str__(self) -> str:
        return f"{self.evidence} → {self.entity_type}#{self.entity_id}"
