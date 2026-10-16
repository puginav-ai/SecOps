"""Реестр ИС (неделя 3): формы, привязка активов, Unknown assets, видимость владельца."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.registry.forms import SystemComponentForm, SystemForm
from apps.registry.models import Asset, Person, System, SystemComponent

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner() -> Person:
    return Person.objects.create(fio="Иванов Иван Иванович", position="Главный врач")


@pytest.fixture
def system(owner: Person) -> System:
    return System.objects.create(
        name="ЛИС-Тест", system_type=System.SystemType.LIS, owner_person=owner
    )


def system_payload(owner: Person) -> dict:
    return {
        "name": "Новая ИС",
        "system_type": System.SystemType.LIS,
        "site": "",
        "control_authority": System.ControlAuthority.UNKNOWN,
        "owner_person": owner.pk,
        "operator_org": "",
        "has_pdn": System.YesNoUnknown.UNKNOWN,
        "kii_scope": System.YesNoUnknown.UNKNOWN,
        "criticality": System.Criticality.LOW,
        "status": System.Status.ACTIVE,
        "notes": "",
    }


# --- формы ---------------------------------------------------------------------------


def test_system_form_requires_owner(owner: Person) -> None:
    data = system_payload(owner)
    data["owner_person"] = ""
    form = SystemForm(data=data)

    assert not form.is_valid()
    assert "owner_person" in form.errors


def test_system_form_requires_authority(owner: Person) -> None:
    data = system_payload(owner)
    data["control_authority"] = ""
    form = SystemForm(data=data)

    assert not form.is_valid()
    assert "control_authority" in form.errors


def test_system_form_accepts_explicit_unknown_authority(owner: Person) -> None:
    form = SystemForm(data=system_payload(owner))

    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.owner_person == owner
    assert saved.control_authority == System.ControlAuthority.UNKNOWN


def test_component_form_rejects_duplicate_link(system: System) -> None:
    asset = Asset.objects.create(ip="10.60.1.10", last_seen_at=timezone.now())
    SystemComponent.objects.create(system=system, asset=asset, role=SystemComponent.Role.SERVER)

    form = SystemComponentForm(
        data={"asset": asset.pk, "role": "server", "note": ""}, system=system
    )

    assert not form.is_valid()
    assert "asset" in form.errors


# --- страницы ------------------------------------------------------------------------


def test_systems_page_requires_login(client) -> None:
    response = client.get("/registry/systems/")

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_systems_page_lists_seeded_systems(client, login, make_user) -> None:
    client = login(make_user("itops-sys", role="it_ops"))

    body = client.get("/registry/systems/").content.decode()

    assert "ЛИС" in body
    assert "Телемедицина" in body  # из начального набора (data migration)


def test_create_system_view_requires_owner(client, login, make_user, owner: Person) -> None:
    client = login(make_user("itops-own", role="it_ops"))
    data = system_payload(owner)
    data["owner_person"] = ""

    response = client.post("/registry/systems/new/", data)

    assert response.status_code == 200  # форма с ошибкой
    assert not System.objects.filter(name="Новая ИС").exists()


def test_create_system_view_saves(client, login, make_user, owner: Person) -> None:
    client = login(make_user("itops-new", role="it_ops"))

    response = client.post("/registry/systems/new/", system_payload(owner))

    assert response.status_code == 302
    assert System.objects.filter(name="Новая ИС", owner_person=owner).exists()


def test_reader_cannot_create_system(client, login, make_user, owner: Person) -> None:
    client = login(make_user("reader-sys", role="reader"))

    response = client.post("/registry/systems/new/", system_payload(owner))

    assert response.status_code == 403


def test_attach_component_removes_from_unknown(client, login, make_user, system: System) -> None:
    asset = Asset.objects.create(
        ip="10.60.1.20", hostname="attach-demo", last_seen_at=timezone.now()
    )
    client = login(make_user("itops-attach", role="it_ops"))
    before = client.get("/registry/assets/unknown/").content.decode()
    assert "attach-demo" in before

    response = client.post(
        f"/registry/systems/{system.pk}/components/add/",
        {"asset": asset.pk, "role": SystemComponent.Role.SERVER, "note": ""},
    )

    assert response.status_code == 302
    assert SystemComponent.objects.filter(system=system, asset=asset).exists()
    body = client.get("/registry/assets/unknown/").content.decode()
    assert "attach-demo" not in body


def test_unknown_assets_shows_only_unassigned(client, login, make_user) -> None:
    free = Asset.objects.create(ip="10.60.9.9", last_seen_at=timezone.now())
    owned = Asset.objects.create(
        ip="10.60.9.10",
        last_seen_at=timezone.now(),
        owner_person=Person.objects.create(fio="Петров Пётр Петрович"),
    )
    client = login(make_user("itops-unknown", role="it_ops"))

    body = client.get("/registry/assets/unknown/").content.decode()

    assert free.ip in body
    assert owned.ip not in body


def test_system_owner_sees_only_own_systems(client, login, make_user) -> None:
    user = make_user("vrach", role="system_owner")
    me = Person.objects.create(fio="Сидоров Сидор Сидорович", user=user)
    mine = System.objects.create(name="Моя ИС", owner_person=me)
    theirs = System.objects.create(
        name="Чужая ИС", owner_person=Person.objects.create(fio="Другой Владелец")
    )
    client = login(user)

    body = client.get("/registry/systems/").content.decode()

    assert "Моя ИС" in body
    assert "Чужая ИС" not in body
    assert client.get(f"/registry/systems/{mine.pk}/").status_code == 200
    assert client.get(f"/registry/systems/{theirs.pk}/").status_code == 404


def test_person_create_view(client, login, make_user) -> None:
    client = login(make_user("itops-person", role="it_ops"))

    response = client.post(
        "/registry/persons/new/",
        {
            "fio": "Новиков Николай Николаевич",
            "position": "Начальник ИТ",
            "phone": "",
            "email": "",
            "user": "",
        },
    )

    assert response.status_code == 302
    assert Person.objects.filter(fio="Новиков Николай Николаевич").exists()
