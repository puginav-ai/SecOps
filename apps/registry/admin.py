"""Админка реестра: справочники и активы. Журнал дрейфа — только чтение."""

from __future__ import annotations

from django.contrib import admin

from apps.registry.models import Asset, AssetEvent, Person, Segment, Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["name", "address"]
    search_fields = ["name", "address"]


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["fio", "position", "phone", "email", "user"]
    search_fields = ["fio", "email"]


@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ["name", "site", "cidr", "vlan", "scan_enabled", "scan_profile", "last_scan_at"]
    list_filter = ["site", "scan_enabled", "scan_profile"]
    search_fields = ["name", "cidr"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["ip", "mac", "hostname", "segment", "device_role", "last_seen_at", "miss_count"]
    list_filter = ["device_role", "criticality", "discovery_source", "site", "segment"]
    search_fields = ["ip", "mac", "hostname"]


@admin.register(AssetEvent)
class AssetEventAdmin(admin.ModelAdmin):
    """Журнал дрейфа — append-only, править нельзя."""

    list_display = ["at", "asset", "kind", "details"]
    list_filter = ["kind"]
    readonly_fields = ["asset", "kind", "at", "details"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
