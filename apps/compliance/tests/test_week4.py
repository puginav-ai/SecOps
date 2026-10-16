"""Неделя 4: каталог, матрица «ИС × контроль», статусные переходы, прогоны проверок."""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from freezegun import freeze_time

from apps.compliance import services
from apps.compliance.models import (
    Control,
    ControlImplementation,
    ControlTest,
    Requirement,
    RequirementControlMap,
    TestRun,
)
from apps.evidence.models import EvidenceObject
from apps.registry.models import Person, System

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner() -> Person:
    return Person.objects.create(fio="Владелец ИС Тестовый")


@pytest.fixture
def system(owner: Person) -> System:
    return System.objects.create(name="ЛИС-Тест", owner_person=owner)


@pytest.fixture
def implementation(system: System) -> ControlImplementation:
    control = Control.objects.get(code="ANTIVIR")
    return ControlImplementation.objects.create(
        control=control,
        system=system,
        is_applicable=True,
        status=ControlImplementation.Status.PLANNED,
    )


def test_seed_catalog_is_idempotent() -> None:
    seed = importlib.import_module("apps.compliance.migrations.0002_seed_catalog").seed_catalog

    seed(django_apps, None)
    before = (
        Requirement.objects.count(),
        Control.objects.count(),
        RequirementControlMap.objects.count(),
        ControlTest.objects.count(),
    )
    seed(django_apps, None)
    after = (
        Requirement.objects.count(),
        Control.objects.count(),
        RequirementControlMap.objects.count(),
        ControlTest.objects.count(),
    )

    assert before == after
    assert Control.objects.count() >= 15
    assert all(control.tests.exists() for control in Control.objects.all())


def test_matrix_creates_pairs_and_requires_login(client, login, make_user, system: System) -> None:
    assert client.get("/compliance/").status_code == 302

    client = login(make_user("officer-mx", role="ib_officer"))
    response = client.get("/compliance/")

    assert response.status_code == 200
    assert ControlImplementation.objects.filter(system=system).count() == Control.objects.count()
    body = response.content.decode()
    assert "ANTIVIR" in body
    assert system.name in body


def test_gap_filter_hides_verified(client, login, make_user, system: System) -> None:
    client = login(make_user("officer-gap", role="ib_officer"))
    client.get("/compliance/")  # создаёт матрицу

    control = Control.objects.get(code="ANTIVIR")
    for implementation in ControlImplementation.objects.filter(control=control):
        implementation.status = ControlImplementation.Status.VERIFIED
        implementation.last_test_at = timezone.now()
        implementation.save(update_fields=["status", "last_test_at"])

    body = client.get("/compliance/?gap=1").content.decode()

    assert control.code not in body
    assert "TRAINING" in body  # другой контроль всё ещё в пробелах


def test_verified_requires_test_run(implementation: ControlImplementation, make_user) -> None:
    officer = make_user("officer-st", role="ib_officer")
    with pytest.raises(ValidationError):
        services.set_status(implementation, ControlImplementation.Status.VERIFIED, officer)

    test = implementation.control.tests.first()
    TestRun.objects.create(test=test, system=implementation.system, result=TestRun.Result.PASS)

    implementation.refresh_from_db()
    services.set_status(implementation, ControlImplementation.Status.VERIFIED, officer)
    implementation.refresh_from_db()

    assert implementation.status == ControlImplementation.Status.VERIFIED


def test_exception_requires_admin_and_review(
    implementation: ControlImplementation, make_user
) -> None:
    officer = make_user("officer-ex", role="ib_officer")
    with pytest.raises(ValidationError):
        services.set_status(implementation, ControlImplementation.Status.EXCEPTION, officer)

    admin = make_user("admin-ex", role="ib_admin")
    with pytest.raises(ValidationError):  # нет обоснования и срока пересмотра
        services.set_status(implementation, ControlImplementation.Status.EXCEPTION, admin)

    implementation.exception_note = "Решение руководства от 01.10.2026"
    implementation.exception_review_at = timezone.now() + timedelta(days=180)
    with pytest.raises(ValidationError):  # нет evidence решения (SDD §4)
        services.set_status(implementation, ControlImplementation.Status.EXCEPTION, admin)

    implementation.exception_evidence = EvidenceObject.objects.create(
        title="Решение руководства", file=SimpleUploadedFile("decision.pdf", b"x")
    )
    services.set_status(implementation, ControlImplementation.Status.EXCEPTION, admin)
    implementation.refresh_from_db()

    assert implementation.status == ControlImplementation.Status.EXCEPTION
    assert implementation.exception_approved_at is not None


def test_na_requires_not_applicable(implementation: ControlImplementation, make_user) -> None:
    officer = make_user("officer-na", role="ib_officer")
    with pytest.raises(ValidationError):
        services.set_status(implementation, ControlImplementation.Status.NA, officer)

    implementation.is_applicable = False
    implementation.save(update_fields=["is_applicable"])
    services.set_status(implementation, ControlImplementation.Status.NA, officer)
    implementation.refresh_from_db()

    assert implementation.status == ControlImplementation.Status.NA


@freeze_time("2026-10-19 09:00:00+05:00")
def test_test_run_updates_due_dates(implementation: ControlImplementation) -> None:
    test = ControlTest.objects.create(
        control=implementation.control,
        test_type=ControlTest.TestType.CONFIG,
        frequency_days=30,
    )

    run = TestRun.objects.create(
        test=test, system=implementation.system, result=TestRun.Result.PASS
    )

    implementation.refresh_from_db()
    assert implementation.last_test_at == run.run_at
    assert implementation.next_due_at == run.run_at + timedelta(days=30)


def test_test_run_view(client, login, make_user, implementation: ControlImplementation) -> None:
    client = login(make_user("officer-run", role="ib_officer"))
    test = implementation.control.tests.first()

    response = client.post(
        f"/compliance/implementations/{implementation.pk}/test/",
        {"test": test.pk, "run_at": "2026-10-19T09:00", "result": "pass", "notes": ""},
    )

    assert response.status_code == 302
    assert TestRun.objects.filter(system=implementation.system, test=test).exists()


def test_implementation_edit_blocks_verified_without_test(
    client, login, make_user, implementation: ControlImplementation
) -> None:
    client = login(make_user("officer-edit", role="ib_officer"))

    response = client.post(
        f"/compliance/implementations/{implementation.pk}/edit/",
        {
            "is_applicable": "on",
            "applicability_reason": "",
            "status": ControlImplementation.Status.VERIFIED,
            "owner_person": "",
            "exception_note": "",
            "exception_review_at": "",
        },
    )

    assert response.status_code == 200  # форма с ошибкой
    implementation.refresh_from_db()
    assert implementation.status == ControlImplementation.Status.PLANNED


def test_implementation_edit_saves_plain_status(
    client, login, make_user, implementation: ControlImplementation
) -> None:
    client = login(make_user("officer-edit2", role="ib_officer"))

    response = client.post(
        f"/compliance/implementations/{implementation.pk}/edit/",
        {
            "is_applicable": "on",
            "applicability_reason": "применяется",
            "status": ControlImplementation.Status.IMPLEMENTED,
            "owner_person": "",
            "exception_note": "",
            "exception_review_at": "",
        },
    )

    assert response.status_code == 302
    implementation.refresh_from_db()
    assert implementation.status == ControlImplementation.Status.IMPLEMENTED
