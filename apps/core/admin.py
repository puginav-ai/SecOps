"""Админка: пользователи (стандартная) и read-only журнал аудита."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.core.models import AuditLog, User

admin.site.register(User, UserAdmin)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("at", "actor", "action", "entity_type", "entity_id", "actor_ip")
    list_filter = ("entity_type",)
    search_fields = ("action", "entity_id", "actor__username")
    date_hierarchy = "at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
