"""Админка КЗИ/ПЗИ."""

from __future__ import annotations

from django.contrib import admin

from apps.kzi.models import (
    Assessment,
    AssessmentPenalty,
    AssessmentSystem,
    KpiGroup,
    KpiItem,
    KpiValue,
    RemediationPlan,
    RemediationTask,
)


class KpiItemInline(admin.TabularInline):
    model = KpiItem
    extra = 0


@admin.register(KpiGroup)
class KpiGroupAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "weight_rj", "sort"]
    inlines = [KpiItemInline]


@admin.register(KpiItem)
class KpiItemAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "group", "max_value", "weight", "is_mandatory"]
    list_filter = ["group", "is_mandatory"]


class KpiValueInline(admin.TabularInline):
    model = KpiValue
    extra = 0


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = [
        "assessment_type",
        "period_label",
        "status",
        "result_value",
        "verdict",
        "assessed_at",
    ]
    list_filter = ["assessment_type", "status"]
    inlines = [KpiValueInline]


@admin.register(AssessmentSystem)
class AssessmentSystemAdmin(admin.ModelAdmin):
    list_display = ["assessment", "system"]


@admin.register(AssessmentPenalty)
class AssessmentPenaltyAdmin(admin.ModelAdmin):
    list_display = ["assessment", "kpi_group", "window_start", "window_end", "cap_value"]


@admin.register(RemediationPlan)
class RemediationPlanAdmin(admin.ModelAdmin):
    list_display = ["title", "assessment", "created_at"]


@admin.register(RemediationTask)
class RemediationTaskAdmin(admin.ModelAdmin):
    list_display = ["title", "plan", "system", "owner_person", "due_at", "status"]
    list_filter = ["status"]
