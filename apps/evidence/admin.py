"""Админка evidence."""

from __future__ import annotations

from django.contrib import admin

from apps.evidence.models import EvidenceLink, EvidenceObject


@admin.register(EvidenceObject)
class EvidenceObjectAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "kind",
        "letter_direction",
        "size",
        "sha256",
        "valid_until",
        "created_at",
    ]
    list_filter = ["kind", "confidentiality", "letter_direction", "reply_status"]
    search_fields = ["title", "letter_number", "correspondent", "sha256"]
    readonly_fields = ["sha256", "size", "filename", "mime", "created_at"]


@admin.register(EvidenceLink)
class EvidenceLinkAdmin(admin.ModelAdmin):
    list_display = ["evidence", "entity_type", "entity_id", "role"]
    list_filter = ["entity_type", "role"]
