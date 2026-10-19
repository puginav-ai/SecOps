"""Dev-режим открытого доступа (ADR §4): вся консоль без входа, от имени OPEN_ACCESS_USER."""

from __future__ import annotations

import pytest

from apps.core.models import AuditLog, User
from apps.registry.models import Segment, Site

pytestmark = pytest.mark.django_db


@pytest.fixture
def open_access(settings, make_user) -> User:
    settings.REGISTRY_OPEN_ACCESS = True
    settings.OPEN_ACCESS_USER = "grc-admin"
    return make_user("grc-admin", role="ib_admin")


def test_mode_off_requires_login(client) -> None:
    response = client.get("/")

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_mode_on_opens_dashboard_and_reports(open_access: User, client) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/reports/").status_code == 200
    assert client.get("/reports/management/").status_code == 200


def test_mode_on_writes_are_attributed_in_audit(open_access: User, client) -> None:
    site = Site.objects.create(name="Площадка-Открытая")
    payload = {
        "site": site.pk,
        "name": "Сегмент-Открытый",
        "cidr": "10.60.8.0/24",
        "vlan": "61",
        "description": "",
        "owner_person": "",
        "scan_profile": Segment.ScanProfile.PING,
        "days": ["0", "1"],
        "start": "08:00",
        "end": "14:00",
    }

    response = client.post("/registry/segments/new/", payload)

    assert response.status_code == 302
    assert Segment.objects.filter(name="Сегмент-Открытый").exists()
    # анонимная мутация привязана к OPEN_ACCESS_USER, а не к пустому актору
    assert AuditLog.objects.filter(actor__username="grc-admin").exists()


def test_mode_on_without_user_stays_registry_only(open_access: User, settings, client) -> None:
    settings.OPEN_ACCESS_USER = ""

    assert client.get("/registry/").status_code == 200  # историческое поведение
    assert client.get("/").status_code == 302  # дашборд по-прежнему просит вход
