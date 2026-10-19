"""Админка инцидентов."""

from __future__ import annotations

from django.contrib import admin

from apps.incidents.models import Incident, IncidentNotification, IncidentNotificationRule


class StageInline(admin.TabularInline):
    model = IncidentNotification
    extra = 0
    readonly_fields = ["stage_code", "deadline_at", "sent_at", "status", "channel", "evidence"]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["pk", "kind", "severity", "detected_at", "system", "status", "closed_at"]
    list_filter = ["kind", "severity", "status"]
    search_fields = ["description"]
    inlines = [StageInline]


@admin.register(IncidentNotificationRule)
class IncidentNotificationRuleAdmin(admin.ModelAdmin):
    list_display = ["stage_code", "kind", "offset_minutes", "target", "template_code"]
    list_filter = ["kind", "target"]


@admin.register(IncidentNotification)
class IncidentNotificationAdmin(admin.ModelAdmin):
    list_display = ["incident", "stage_code", "deadline_at", "sent_at", "status", "channel"]
    list_filter = ["status", "channel", "stage_code"]
