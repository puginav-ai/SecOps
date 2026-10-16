"""Админка обязательств."""

from __future__ import annotations

from django.contrib import admin

from apps.obligations.models import ObligationInstance, ObligationTemplate


@admin.register(ObligationTemplate)
class ObligationTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "kind",
        "recurrence_rule",
        "lead_days",
        "owner_role",
        "requires_closing_evidence",
    ]
    list_filter = ["kind", "owner_role", "requires_closing_evidence"]
    search_fields = ["name"]


@admin.register(ObligationInstance)
class ObligationInstanceAdmin(admin.ModelAdmin):
    list_display = ["template", "due_at", "status", "owner_person", "escalation_level", "closed_at"]
    list_filter = ["status", "template__kind"]
    search_fields = ["template__name", "owner_person__fio"]
    autocomplete_fields = ["owner_person"]
