"""Админка уведомлений."""

from __future__ import annotations

from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "channel", "kind", "recipient_user", "recipient_email"]
    list_filter = ["channel", "kind"]
    search_fields = ["recipient_email", "message"]
    readonly_fields = ["created_at", "dedup_key"]
