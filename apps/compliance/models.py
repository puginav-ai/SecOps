"""Нормативка → контроли → проверки (SDD §3.2, неделя 4)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Domain(models.TextChoices):
    KII = "kii", "КИИ"
    PDN = "pdn", "ПДн"
    SKZI = "skzi", "СКЗИ"
    MEDICAL = "medical", "Медицина"
    OTHER = "other", "Прочее"


class NormAct(models.Model):
    """НПА (117/КИИ, 152-ФЗ, приказы ФСТЭК, регламенты СКЗИ)."""

    name = models.CharField("название", max_length=200)
    version = models.CharField("версия", max_length=50, blank=True, default="")
    effective_from = models.DateField("дата вступления", null=True, blank=True)
    note = models.TextField("примечание", blank=True, default="")

    class Meta:
        verbose_name = "НПА"
        verbose_name_plural = "НПА (каталог)"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Requirement(models.Model):
    """Атомарный пункт требования из НПА."""

    norm_act = models.ForeignKey(
        NormAct, verbose_name="НПА", on_delete=models.PROTECT, related_name="requirements"
    )
    domain = models.CharField("домен", max_length=10, choices=Domain.choices, default=Domain.OTHER)
    clause = models.CharField("пункт", max_length=100)
    text = models.TextField("формулировка")

    class Meta:
        verbose_name = "Требование"
        verbose_name_plural = "Требования"
        ordering = ["norm_act__name", "clause"]

    def __str__(self) -> str:
        return f"{self.norm_act} {self.clause}"


class Control(models.Model):
    """Мера/контроль из каталога («топ-15» на старте)."""

    code = models.CharField("код", max_length=30, unique=True)
    name = models.CharField("название", max_length=200)
    domain = models.CharField("домен", max_length=10, choices=Domain.choices, default=Domain.OTHER)
    description = models.TextField("описание", blank=True, default="")

    class Meta:
        verbose_name = "Контроль"
        verbose_name_plural = "Контроли (каталог)"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class RequirementControlMap(models.Model):
    """M:N: требование ↔ контроль (SDD §3.2)."""

    requirement = models.ForeignKey(
        Requirement, on_delete=models.CASCADE, related_name="control_links"
    )
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name="requirement_links")

    class Meta:
        verbose_name = "Требование ↔ контроль"
        verbose_name_plural = "Требования ↔ контроли"
        constraints = [
            models.UniqueConstraint(fields=["requirement", "control"], name="uniq_req_control")
        ]

    def __str__(self) -> str:
        return f"{self.requirement} ↔ {self.control.code}"


class ControlTest(models.Model):
    """Проверка контроля: тип, периодичность, критерий, виды evidence."""

    class TestType(models.TextChoices):
        DOCUMENT = "document", "документ"
        CONFIG = "config", "конфигурация"
        INTERVIEW = "interview", "интервью"
        SCAN = "scan", "скан/техническая проверка"
        RESTORE = "restore", "восстановление"
        OTHER = "other", "прочее"

    control = models.ForeignKey(
        Control, verbose_name="контроль", on_delete=models.CASCADE, related_name="tests"
    )
    test_type = models.CharField("тип", max_length=10, choices=TestType.choices)
    frequency_days = models.PositiveIntegerField("периодичность, дней", null=True, blank=True)
    pass_criteria = models.TextField("критерий прохождения", blank=True, default="")
    evidence_kinds = models.JSONField("виды evidence", default=list, blank=True)
    is_mandatory = models.BooleanField("обязательная", default=False)

    class Meta:
        verbose_name = "Проверка контроля"
        verbose_name_plural = "Проверки контролей"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.control.code}: {self.get_test_type_display()}"


class ControlImplementation(models.Model):
    """Контроль, применимый к ИС (строка матрицы «ИС × контроль», SDD §3.2)."""

    class Status(models.TextChoices):
        NA = "na", "Не применимо"
        PLANNED = "planned", "Запланировано"
        IMPLEMENTED = "implemented", "Внедрено"
        VERIFIED = "verified", "Подтверждено"
        NON_COMPLIANT = "non_compliant", "Не соответствует"
        EXTERNAL = "external", "Внешняя зависимость"
        EXCEPTION = "exception", "Исключение (решение руководства)"

    control = models.ForeignKey(
        Control, verbose_name="контроль", on_delete=models.PROTECT, related_name="implementations"
    )
    system = models.ForeignKey(
        "registry.System",
        verbose_name="ИС",
        on_delete=models.PROTECT,
        related_name="control_implementations",
    )
    owner_person = models.ForeignKey(
        "registry.Person",
        verbose_name="ответственный",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="control_implementations",
    )
    is_applicable = models.BooleanField("применимо", default=True)
    applicability_reason = models.CharField(
        "обоснование применимости", max_length=200, blank=True, default=""
    )
    status = models.CharField(
        "статус", max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    last_test_at = models.DateTimeField("последняя проверка", null=True, blank=True)
    next_due_at = models.DateTimeField("следующая проверка", null=True, blank=True)
    exception_note = models.TextField("обоснование исключения", blank=True, default="")
    exception_evidence = models.ForeignKey(
        "evidence.EvidenceObject",
        verbose_name="evidence решения руководителя",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exception_implementations",
    )
    exception_approved_at = models.DateTimeField("исключение утверждено", null=True, blank=True)
    exception_review_at = models.DateTimeField("пересмотр исключения", null=True, blank=True)

    class Meta:
        verbose_name = "Контроль по ИС"
        verbose_name_plural = "Матрица «ИС × контроль»"
        constraints = [
            models.UniqueConstraint(fields=["control", "system"], name="uniq_control_system")
        ]
        ordering = ["control__code", "system__name"]

    def __str__(self) -> str:
        return f"{self.control.code} @ {self.system}"


class TestRun(models.Model):
    """Факт проверки контроля по ИС; пересчитывает next_due_at (SDD §3.2, §5.3)."""

    __test__ = False  # модель, а не тест-класс (pytest)

    class Result(models.TextChoices):
        PASS = "pass", "пройдено"
        FAIL = "fail", "не пройдено"
        PARTIAL = "partial", "частично"

    test = models.ForeignKey(
        ControlTest, verbose_name="проверка", on_delete=models.PROTECT, related_name="runs"
    )
    system = models.ForeignKey(
        "registry.System", verbose_name="ИС", on_delete=models.PROTECT, related_name="test_runs"
    )
    run_at = models.DateTimeField("когда выполнена", default=timezone.now)
    result = models.CharField("результат", max_length=10, choices=Result.choices)
    evidence = models.ForeignKey(
        "evidence.EvidenceObject",
        verbose_name="основное доказательство",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="test_runs",
    )
    notes = models.TextField("заметки", blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="записал",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="test_runs",
    )

    class Meta:
        verbose_name = "Прогон проверки"
        verbose_name_plural = "Прогоны проверок"
        ordering = ["-run_at"]

    def __str__(self) -> str:
        return f"{self.test.control.code} @ {self.system} ({self.get_result_display()})"

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        implementation = ControlImplementation.objects.filter(
            control=self.test.control, system=self.system
        ).first()
        if implementation is not None:
            implementation.last_test_at = self.run_at
            implementation.next_due_at = (
                self.run_at + timedelta(days=self.test.frequency_days)
                if self.test.frequency_days
                else None
            )
            implementation.save(update_fields=["last_test_at", "next_due_at"])
        if self.evidence_id:
            # Основное доказательство прогона = связь role=proof (SDD §3.3)
            from apps.evidence.models import EvidenceLink  # локальный импорт: без циклов

            EvidenceLink.objects.get_or_create(
                evidence_id=self.evidence_id,
                entity_type="test_run",
                entity_id=self.pk,
                role=EvidenceLink.Role.PROOF,
            )
