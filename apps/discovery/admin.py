"""Админка discovery: журнал сканов — только чтение."""

from __future__ import annotations

from django.contrib import admin

from apps.discovery.models import ScanRun


@admin.register(ScanRun)
class ScanRunAdmin(admin.ModelAdmin):
    list_display = ["started_at", "segment", "status", "triggered_by", "finished_at"]
    list_filter = ["status", "triggered_by", "segment"]
    readonly_fields = ["segment", "started_at", "finished_at", "status", "stats", "triggered_by"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
