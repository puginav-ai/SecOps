"""КЗИ/ПЗИ: каталог KPI, оценки, значения, штрафы-капы, планы мероприятий (SDD §3.4)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class KpiGroup(models.Model):
    """Группа KPI с весом в итоговой оценке; Σ weight_rj = 1."""

    code = models.CharField("код", max_length=20, unique=True)
    name = models.CharField("название", max_length=200)
    weight_rj = models.DecimalField("вес группы", max_digits=6, decimal_places=4)
    sort = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        verbose_name = "Группа KPI"
        verbose_name_plural = "Группы KPI"
        ordering = ["sort", "code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class KpiItem(models.Model):
    """KPI внутри группы; вес — внутри группы (SDD §3.4)."""

    group = models.ForeignKey(
        KpiGroup, verbose_name="группа", on_delete=models.PROTECT, related_name="items"
    )
    code = models.CharField("код", max_length=30, unique=True)
    name = models.CharField("название", max_length=200)
    max_value = models.DecimalField("максимум", max_digits=6, decimal_places=2, default=1)
    weight = models.DecimalField("вес", max_digits=6, decimal_places=4, default=1)
    is_mandatory = models.BooleanField("обязательный", default=False)
    sort = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        verbose_name = "KPI"
        verbose_name_plural = "KPI (показатели)"
        ordering = ["group__sort", "sort", "code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Assessment(models.Model):
    """Оценка КЗИ/ПЗИ: скоуп ИС, период, статус, результат и снапшот расчёта."""

    class AssessmentType(models.TextChoices):
        KZI = "kzi", "КЗИ"
        PZI = "pzi", "ПЗИ"

    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        INCOMPLETE = "incomplete", "не заполнена"
        SUBMITTED = "submitted", "передана"
        CLOSED = "closed", "закрыта"

    assessment_type = models.CharField("тип", max_length=3, choices=AssessmentType.choices)
    period_label = models.CharField("период (подпись)", max_length=100, blank=True, default="")
    period_start = models.DateField("начало периода", null=True, blank=True)
    period_end = models.DateField("конец периода", null=True, blank=True)
    status = models.CharField("статус", max_length=12, choices=Status.choices, default=Status.DRAFT)
    assessed_at = models.DateTimeField("рассчитана", null=True, blank=True)
    result_value = models.DecimalField(
        "итог", max_digits=6, decimal_places=4, null=True, blank=True
    )
    verdict = models.CharField("вердикт", max_length=20, blank=True, default="")
    details = models.JSONField("снапшот расчёта", default=dict, blank=True)
    systems = models.ManyToManyField(
        "registry.System",
        verbose_name="ИС в скоупе",
        related_name="assessments",
        through="AssessmentSystem",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="создал",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments",
    )
    created_at = models.DateTimeField("создана", auto_now_add=True)

    class Meta:
        verbose_name = "Оценка КЗИ/ПЗИ"
        verbose_name_plural = "Оценки КЗИ/ПЗИ"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_assessment_type_display()} {self.period_label or self.pk}"


class AssessmentSystem(models.Model):
    """Скоуп оценки: ИС в оценке."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="scope")
    system = models.ForeignKey(
        "registry.System", on_delete=models.PROTECT, related_name="assessment_scope"
    )

    class Meta:
        verbose_name = "ИС в оценке"
        verbose_name_plural = "ИС в оценках"
        constraints = [
            models.UniqueConstraint(fields=["assessment", "system"], name="uniq_assessment_system")
        ]

    def __str__(self) -> str:
        return f"{self.assessment} ← {self.system}"


class KpiValue(models.Model):
    """Значение KPI по ИС в оценке; NULL = нет данных (≠ 0)."""

    class Source(models.TextChoices):
        MANUAL = "manual", "вручную"
        TEST = "test", "проверка контроля"
        MEASURE = "measure", "измерение"
        EXPERT = "expert", "экспертно"

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="values")
    system = models.ForeignKey(
        "registry.System", on_delete=models.PROTECT, related_name="kpi_values"
    )
    kpi_item = models.ForeignKey(KpiItem, on_delete=models.PROTECT, related_name="values")
    value = models.DecimalField("значение", max_digits=8, decimal_places=2, null=True, blank=True)
    source = models.CharField(
        "источник", max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    evidence = models.ForeignKey(
        "evidence.EvidenceObject",
        verbose_name="evidence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kpi_values",
    )
    note = models.CharField("примечание", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "Значение KPI"
        verbose_name_plural = "Значения KPI"
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "system", "kpi_item"], name="uniq_kpi_value"
            )
        ]
        ordering = ["system__name", "kpi_item__group__sort", "kpi_item__sort"]

    def __str__(self) -> str:
        return f"{self.system} {self.kpi_item.code}={self.value}"


class AssessmentPenalty(models.Model):
    """Штраф-«потолок» группы в окне (SDD §3.4)."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="penalties")
    kpi_group = models.ForeignKey(KpiGroup, on_delete=models.PROTECT, related_name="penalties")
    window_start = models.DateField("окно с")
    window_end = models.DateField("окно по")
    reason = models.CharField("причина", max_length=200)
    cap_value = models.DecimalField("потолок", max_digits=6, decimal_places=4)
    triggered_by = models.CharField("источник", max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Штраф (кап) группы"
        verbose_name_plural = "Штрафы (капы) групп"
        ordering = ["kpi_group__sort"]

    def __str__(self) -> str:
        return f"{self.kpi_group.code} ≤ {self.cap_value}"


class RemediationPlan(models.Model):
    """План мероприятий из «почему не 1» (SDD §3.4, неделя 9)."""

    assessment = models.ForeignKey(
        Assessment,
        verbose_name="оценка",
        on_delete=models.PROTECT,
        related_name="remediation_plans",
    )
    title = models.CharField("название", max_length=200)
    created_at = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        verbose_name = "План мероприятий"
        verbose_name_plural = "Планы мероприятий"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class RemediationTask(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "открыта"
        DONE = "done", "выполнена"
        CANCELLED = "cancelled", "отменена"

    plan = models.ForeignKey(RemediationPlan, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField("задача", max_length=300)
    system = models.ForeignKey(
        "registry.System",
        verbose_name="ИС",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="remediation_tasks",
    )
    kpi_item = models.ForeignKey(
        KpiItem,
        verbose_name="KPI",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="remediation_tasks",
    )
    owner_person = models.ForeignKey(
        "registry.Person",
        verbose_name="ответственный",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="remediation_tasks",
    )
    due_at = models.DateField("срок", null=True, blank=True)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.OPEN)
    evidence = models.ForeignKey(
        "evidence.EvidenceObject",
        verbose_name="evidence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remediation_tasks",
    )

    class Meta:
        verbose_name = "Задача плана"
        verbose_name_plural = "Задачи планов"
        ordering = ["due_at", "title"]

    def __str__(self) -> str:
        return self.title
