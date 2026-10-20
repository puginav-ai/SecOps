"""Штатный пересчёт производных полей актива после смены правил (SDD §5.10)."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.registry.models import Asset, Segment, Site

pytestmark = pytest.mark.django_db


def test_reclassify_assets_refreshes_stale_role() -> None:
    site = Site.objects.create(name="Площадка-Пересчёт")
    segment = Segment.objects.create(site=site, name="Сегмент-Пересчёт", cidr="10.80.1.0/24")
    asset = Asset.objects.create(
        ip="10.80.1.10",
        segment=segment,
        site=site,
        mac_vendor="ASRock Incorporation",
        ports=[21, 135, 139, 445, 5060],  # софтфон, но это АРМ по вендору
        role_auto="phone",
        last_seen_at=timezone.now(),
    )

    call_command("reclassify_assets")

    asset.refresh_from_db()
    assert asset.role_auto == "workstation"
