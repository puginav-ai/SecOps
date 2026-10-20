"""Пересчёт производных полей актива по текущим правилам классификации (SDD §5.10).

Запуск после изменения правил (вендоры/порты/ОС), чтобы не ждать следующего скана:
    python manage.py reclassify_assets
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.registry.models import Asset
from collector.classify import (
    better_os_family,
    classify_role,
    derive_os_family,
    distro_from_services,
)


class Command(BaseCommand):
    help = "Пересчитать role_auto и os_family у всех активов по текущим правилам"

    def handle(self, *args, **options) -> None:
        roles = families = 0
        for asset in Asset.objects.iterator():
            role = classify_role(asset.ports or [], asset.mac_vendor, asset.hostname)
            if role != asset.role_auto and (role or not asset.role_auto):
                asset.role_auto = role
                asset.save(update_fields=["role_auto"])
                roles += 1
            if asset.os_name:
                continue
            family = better_os_family(
                asset.os_family,
                distro_from_services((asset.fingerprint or {}).get("services", []))
                or derive_os_family(asset.ports or [], asset.mac_vendor),
            )
            if family and family != asset.os_family:
                asset.os_family = family
                asset.save(update_fields=["os_family"])
                families += 1
        self.stdout.write(self.style.SUCCESS(f"роли обновлены: {roles}, ОС: {families}"))
