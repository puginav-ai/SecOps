"""Регресс-тесты безопасности (после security-review 16.10.2026): IDOR и CSV-инъекции."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.compliance.models import Control, ControlImplementation
from apps.compliance.services import set_status
from apps.evidence.models import EvidenceLink, EvidenceObject
from apps.obligations.models import ObligationInstance, ObligationTemplate
from apps.registry.models import Person, System

pytestmark = pytest.mark.django_db


@pytest.fixture
def other_person() -> Person:
    return Person.objects.create(fio="Чужой Владелец")


@pytest.fixture
def owner_user(make_user) -> tuple:
    user = make_user("owner-sec", role="system_owner")
    person = Person.objects.create(fio="Свой Владелец", user=user)
    my_system = System.objects.create(name="Своя ИС", owner_person=person)
    return user, person, my_system


def test_owner_cannot_edit_foreign_system(client, login, owner_user, other_person) -> None:
    _user, _person, my_system = owner_user
    foreign = System.objects.create(name="Чужая ИС", owner_person=other_person)
    client = login(_user)

    assert client.get(f"/registry/systems/{foreign.pk}/").status_code == 404
    assert client.get(f"/registry/systems/{foreign.pk}/edit/").status_code == 404
    assert client.get(f"/registry/systems/{my_system.pk}/edit/").status_code == 200


def test_owner_cannot_edit_foreign_implementation(client, login, owner_user, other_person) -> None:
    user, _person, my_system = owner_user
    foreign_system = System.objects.create(name="Чужая-К", owner_person=other_person)
    foreign_impl = ControlImplementation.objects.create(
        control=Control.objects.get(code="ANTIVIR"), system=foreign_system
    )
    my_impl = ControlImplementation.objects.create(
        control=Control.objects.get(code="ANTIVIR"), system=my_system
    )
    client = login(user)

    response = client.post(
        f"/compliance/implementations/{foreign_impl.pk}/edit/",
        {"status": "implemented", "is_applicable": "on"},
    )
    assert response.status_code == 404
    foreign_impl.refresh_from_db()
    assert foreign_impl.status == ControlImplementation.Status.PLANNED

    assert client.get(f"/compliance/implementations/{my_impl.pk}/test/").status_code == 200


def test_owner_cannot_close_foreign_obligation(client, login, owner_user, other_person) -> None:
    user, person, _my_system = owner_user
    template = ObligationTemplate.objects.create(kind="other", name="Обязательство-тест")
    foreign = ObligationInstance.objects.create(
        template=template, due_at=timezone.now(), owner_person=other_person
    )
    mine = ObligationInstance.objects.create(
        template=template, due_at=timezone.now(), owner_person=person
    )
    client = login(user)

    assert client.post(f"/obligations/{foreign.pk}/cancel/").status_code == 404
    assert client.post(f"/obligations/{mine.pk}/cancel/").status_code == 302


def test_owner_cannot_download_foreign_evidence(client, login, owner_user, other_person) -> None:
    user, person, my_system = owner_user
    foreign = EvidenceObject.objects.create(
        title="Чужой документ", file=SimpleUploadedFile("f.pdf", b"x")
    )
    mine = EvidenceObject.objects.create(
        title="Свой документ", file=SimpleUploadedFile("m.pdf", b"x")
    )
    EvidenceLink.objects.create(evidence=mine, entity_type="system", entity_id=my_system.pk)
    client = login(user)

    assert client.get(f"/evidence/{foreign.pk}/download/").status_code == 404
    assert client.get(f"/evidence/{mine.pk}/download/").status_code == 200
    assert client.get(f"/evidence/{foreign.pk}/").status_code == 404
    # «свой» документ виден только через связь со своей ИС
    body = client.get("/evidence/").content.decode()
    assert "Свой документ" in body
    assert "Чужой документ" not in body


def test_csv_export_neutralizes_formulas(client, login, make_user, other_person) -> None:
    system = System.objects.create(name="=cmd|' /C calc'!A0", owner_person=other_person)
    ControlImplementation.objects.create(
        control=Control.objects.get(code="ANTIVIR"),
        system=system,
        status=ControlImplementation.Status.PLANNED,
    )
    client = login(make_user("officer-csvsec", role="ib_officer"))

    body = client.get("/reports/gaps.csv").content.decode("utf-8-sig")

    assert "'=cmd" in body  # формула нейтрализована апострофом
    assert "\n=cmd" not in body


def test_evidence_expiring_bad_days_param(client, login, make_user) -> None:
    client = login(make_user("officer-days", role="ib_officer"))

    assert client.get("/evidence/expiring/?days=abc").status_code == 200
    assert client.get("/evidence/expiring/?days=99999").status_code == 200


def test_exception_requires_evidence(make_user, other_person) -> None:
    admin = make_user("admin-sec", role="ib_admin")
    system = System.objects.create(name="ИС-Искл", owner_person=other_person)
    implementation = ControlImplementation.objects.create(
        control=Control.objects.get(code="ANTIVIR"), system=system
    )
    implementation.exception_note = "Решение руководства"
    implementation.exception_review_at = timezone.now() + timedelta(days=90)

    with pytest.raises(ValidationError) as excinfo:
        set_status(implementation, ControlImplementation.Status.EXCEPTION, admin)
    assert "evidence" in str(excinfo.value)

    evidence = EvidenceObject.objects.create(
        title="Решение", file=SimpleUploadedFile("decision.pdf", b"x")
    )
    implementation.exception_evidence = evidence
    set_status(implementation, ControlImplementation.Status.EXCEPTION, admin)
    implementation.refresh_from_db()
    assert implementation.status == ControlImplementation.Status.EXCEPTION


def test_link_form_rejects_missing_entity(client, login, make_user) -> None:
    client = login(make_user("officer-linksec", role="ib_officer"))
    evidence = EvidenceObject.objects.create(
        title="Документ", file=SimpleUploadedFile("d.pdf", b"x")
    )

    response = client.post(
        f"/evidence/{evidence.pk}/link/",
        {"entity_type": "system", "entity_id": 999999, "role": "proof"},
        follow=True,
    )

    assert response.status_code == 200
    assert not EvidenceLink.objects.filter(evidence=evidence).exists()


def test_owner_only_csv_scoped_to_own(client, login, owner_user, other_person) -> None:
    user, person, my_system = owner_user
    foreign_system = System.objects.create(name="Чужая-Эксп", owner_person=other_person)
    for system in (my_system, foreign_system):
        ControlImplementation.objects.create(
            control=Control.objects.get(code="ANTIVIR"),
            system=system,
            status=ControlImplementation.Status.PLANNED,
        )
    client = login(user)

    body = client.get("/reports/gaps.csv").content.decode("utf-8-sig")

    assert "Своя ИС" in body
    assert "Чужая-Эксп" not in body
