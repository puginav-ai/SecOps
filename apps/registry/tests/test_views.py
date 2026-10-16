"""UI реестра: роли, CRUD сегментов, обзор активов (SDD §4, §5.1–5.2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.registry.models import Asset, Segment, Site

pytestmark = pytest.mark.django_db


@pytest.fixture
def site() -> Site:
    return Site.objects.create(name="Площадка-Демо")


@pytest.fixture
def segment(site: Site) -> Segment:
    return Segment.objects.create(site=site, name="Сегмент-Ночной", cidr="10.60.1.0/24")


def create_payload(site: Site) -> dict:
    return {
        "site": site.pk,
        "name": "Сегмент-Демо",
        "cidr": "10.60.9.0/24",
        "vlan": "60",
        "description": "тестовый сегмент",
        "owner_person": "",
        "scan_profile": Segment.ScanProfile.PING,
        "days": ["0", "1"],
        "start": "23:00",
        "end": "05:00",
    }


def test_segments_page_requires_login(client) -> None:
    response = client.get("/registry/")

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_open_mode_allows_anonymous_read_and_write(client, settings, site: Site) -> None:
    """Временный dev-режим (ADR §4): реестр открыт без входа — чтение и правка."""
    settings.REGISTRY_OPEN_ACCESS = True

    assert client.get("/registry/").status_code == 200
    assert client.get("/registry/assets/").status_code == 200

    response = client.post("/registry/segments/new/", create_payload(site))

    assert response.status_code == 302
    assert Segment.objects.count() == 1


def test_open_mode_keeps_rbac_for_authenticated_users(
    login, make_user, settings, site: Site
) -> None:
    settings.REGISTRY_OPEN_ACCESS = True
    client = login(make_user("reader", role="reader"))

    # вошедшему «Руководству» режим ничего не расширяет: запись по-прежнему запрещена
    assert client.post("/registry/segments/new/", create_payload(site)).status_code == 403


def test_reader_can_view_but_not_edit(login, make_user, segment: Segment, site: Site) -> None:
    client = login(make_user("reader", role="reader"))

    assert client.get("/registry/").status_code == 200
    response = client.post("/registry/segments/new/", create_payload(site))

    assert response.status_code == 403
    assert Segment.objects.count() == 1


def test_it_ops_creates_segment_via_form(login, make_user, site: Site) -> None:
    client = login(make_user("itops", role="it_ops"))

    response = client.post("/registry/segments/new/", create_payload(site))

    assert response.status_code == 302
    segment = Segment.objects.get()
    assert (segment.name, segment.cidr, segment.vlan) == ("Сегмент-Демо", "10.60.9.0/24", 60)
    assert segment.scan_window["days"] == [0, 1]


def test_delete_protected_segment_shows_error(login, make_user, segment: Segment) -> None:
    Asset.objects.create(
        ip="10.60.1.10", site=segment.site, segment=segment, last_seen_at=timezone.now()
    )
    client = login(make_user("itops", role="it_ops"))

    response = client.post(f"/registry/segments/{segment.pk}/delete/", follow=True)

    assert Segment.objects.filter(pk=segment.pk).exists()
    assert "есть активы" in response.content.decode()


def test_delete_empty_segment(login, make_user, segment: Segment) -> None:
    client = login(make_user("itops", role="it_ops"))

    response = client.post(f"/registry/segments/{segment.pk}/delete/")

    assert response.status_code == 302
    assert not Segment.objects.filter(pk=segment.pk).exists()


def test_assets_overview_shows_new_and_distribution(login, make_user, segment: Segment) -> None:
    now = timezone.now()
    Asset.objects.create(
        ip="10.60.1.10", hostname="srv-demo", site=segment.site, segment=segment, last_seen_at=now
    )
    Asset.objects.create(
        ip="10.60.1.11",
        site=segment.site,
        segment=segment,
        last_seen_at=now - timedelta(days=3),
    )
    client = login(make_user("boss", role="ib_admin"))

    body = client.get("/registry/assets/").content.decode()

    assert "10.60.1.10" in body and "10.60.1.11" in body
    assert "Площадка-Демо" in body
    assert "новый" in body


def test_assets_overview_filters_by_segment(login, make_user, site: Site, segment: Segment) -> None:
    other = Segment.objects.create(site=site, name="Сегмент-Другой", cidr="10.60.2.0/24")
    now = timezone.now()
    Asset.objects.create(ip="10.60.1.10", site=site, segment=segment, last_seen_at=now)
    Asset.objects.create(ip="10.60.2.10", site=site, segment=other, last_seen_at=now)
    client = login(make_user("itops", role="it_ops"))

    body = client.get(f"/registry/assets/?segment={segment.pk}").content.decode()

    assert "10.60.1.10" in body
    assert "10.60.2.10" not in body
