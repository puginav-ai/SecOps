"""Админка контролей и проверок."""

from __future__ import annotations

from django.contrib import admin

from apps.compliance.models import (
    Control,
    ControlImplementation,
    ControlTest,
    NormAct,
    Requirement,
    RequirementControlMap,
    TestRun,
)


@admin.register(NormAct)
class NormActAdmin(admin.ModelAdmin):
    list_display = ["name", "version", "effective_from"]
    search_fields = ["name"]


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = ["norm_act", "domain", "clause", "text"]
    list_filter = ["domain", "norm_act"]
    search_fields = ["clause", "text"]


@admin.register(Control)
class ControlAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "domain"]
    list_filter = ["domain"]
    search_fields = ["code", "name"]


@admin.register(RequirementControlMap)
class RequirementControlMapAdmin(admin.ModelAdmin):
    list_display = ["requirement", "control"]


@admin.register(ControlTest)
class ControlTestAdmin(admin.ModelAdmin):
    list_display = ["control", "test_type", "frequency_days", "is_mandatory"]
    list_filter = ["test_type", "is_mandatory"]


@admin.register(ControlImplementation)
class ControlImplementationAdmin(admin.ModelAdmin):
    list_display = ["control", "system", "status", "is_applicable", "last_test_at", "next_due_at"]
    list_filter = ["status", "is_applicable", "control"]
    search_fields = ["control__code", "control__name", "system__name"]


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = ["test", "system", "run_at", "result", "created_by"]
    list_filter = ["result"]
