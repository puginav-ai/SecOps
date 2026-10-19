"""Неделя 10: инциденты — таймеры стадий, evidence отправки, закрытие, эскалации."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from freezegun import freeze_time

from apps.evidence.models import EvidenceObject
from apps.incidents import services
from apps.incidents.models import Incident
from apps.notifications.models import Notification
from apps.registry.models import Person, System

pytestmark = pytest.mark.django_db


@pytest.fixture
def kii_system() -> System:
    owner = Person.objects.create(fio="Владелец ИБ Тестовый")
    return System.objects.create(name="ЛИС-Инцидент", owner_person=owner, kii_scope="yes")


@pytest.fixture
def evidence() -> EvidenceObject:
    return EvidenceObject.objects.create(
        title="Письмо регулятору", file=SimpleUploadedFile("letter.pdf", b"x")
    )


@freeze_time("2026-10-19 08:00:00+05:00")
def test_stage_deadlines_from_rules(kii_system: System) -> None:
    detected = timezone.now()

    incident = services.create_incident(
        kind=Incident.Kind.KII,
        detected_at=detected,
        system=kii_system,
        severity=Incident.Severity.HIGH,
        description="Тестовый инцидент",
    )

    deadlines = {stage.stage_code: stage.deadline_at for stage in incident.stages.all()}
    assert deadlines["1h"] == detected + timedelta(minutes=60)
    assert deadlines["T1"] == detected + timedelta(minutes=240)
    assert deadlines["T2"] == detected + timedelta(minutes=1440)
    assert deadlines["regulator_24"] == detected + timedelta(minutes=1440)
    assert "pdn_24" not in deadlines  # правило ПДн не применяется к КИИ


def test_kii_rules_require_kii_scope() -> None:
    owner = Person.objects.create(fio="Владелец Обычной ИС")
    plain = System.objects.create(name="Не-КИИ", owner_person=owner)

    incident = services.create_incident(
        kind=Incident.Kind.KII,
        detected_at=timezone.now(),
        system=plain,
        severity=Incident.Severity.LOW,
        description="x",
    )

    codes = set(incident.stages.values_list("stage_code", flat=True))
    assert "1h" not in codes
    assert "regulator_24" not in codes
    assert "T1" in codes and "T2" in codes


@freeze_time("2026-10-19 08:00:00+05:00")
def test_stage_overdue_property(kii_system: System) -> None:
    incident = services.create_incident(
        kind=Incident.Kind.OTHER,
        detected_at=timezone.now(),
        system=kii_system,
        severity=Incident.Severity.LOW,
        description="x",
    )
    stage = incident.stages.get(stage_code="T1")

    with freeze_time(timezone.now() + timedelta(minutes=239)):
        assert not stage.is_overdue
    with freeze_time(timezone.now() + timedelta(minutes=241)):
        assert stage.is_overdue


def test_stage_close_requires_evidence(kii_system: System, evidence: EvidenceObject) -> None:
    incident = services.create_incident(
        kind=Incident.Kind.OTHER,
        detected_at=timezone.now(),
        system=kii_system,
        severity=Incident.Severity.LOW,
        description="x",
    )
    stage = incident.stages.get(stage_code="T1")

    with pytest.raises(ValidationError):
        services.mark_stage_sent(stage, evidence=None, channel="email")

    services.mark_stage_sent(stage, evidence=evidence, channel="email")
    stage.refresh_from_db()
    assert stage.status == "sent"
    assert stage.sent_at is not None
    assert stage.evidence_id == evidence.pk

    with pytest.raises(ValidationError):  # повторная отправка запрещена
        services.mark_stage_sent(stage, evidence=evidence, channel="email")


def test_incident_close_blocked_with_open_stages(
    kii_system: System, evidence: EvidenceObject
) -> None:
    incident = services.create_incident(
        kind=Incident.Kind.OTHER,
        detected_at=timezone.now(),
        system=kii_system,
        severity=Incident.Severity.LOW,
        description="x",
    )

    with pytest.raises(ValidationError):
        services.close_incident(incident)

    for stage in incident.stages.all():
        services.mark_stage_sent(stage, evidence=evidence, channel="email")
    services.close_incident(incident)
    incident.refresh_from_db()
    assert incident.status == Incident.Status.CLOSED
    assert incident.closed_at is not None


def test_creation_notifies_role_users(make_user) -> None:
    make_user("admin-inc", role="ib_admin")

    incident = services.create_incident(
        kind=Incident.Kind.OTHER,
        detected_at=timezone.now(),
        severity=Incident.Severity.LOW,
        description="x",
    )

    assert Notification.objects.filter(kind="incident_stage", incident=incident).exists()
    stage = incident.stages.first()
    assert services.notify_stage(stage) == 0  # дедупликация


@freeze_time("2026-10-20 09:00:00+05:00")
def test_overdue_escalation_once_per_day(make_user) -> None:
    make_user("admin-esc2", role="ib_admin")
    services.create_incident(
        kind=Incident.Kind.OTHER,
        detected_at=timezone.now() - timedelta(days=2),
        severity=Incident.Severity.LOW,
        description="Просроченный инцидент",
    )

    first = services.escalate_overdue(timezone.now())
    again = services.escalate_overdue(timezone.now())

    assert first >= 1
    assert again == 0
    with freeze_time(timezone.now() + timedelta(days=1)):
        assert services.escalate_overdue(timezone.now()) >= 1


def test_views_flow(client, login, make_user, kii_system: System) -> None:
    client = login(make_user("officer-inc", role="ib_officer"))

    response = client.post(
        "/incidents/new/",
        {
            "kind": "kii",
            "detected_at": "2026-10-19T09:00",
            "system": kii_system.pk,
            "severity": "high",
            "description": "Тестовый инцидент из UI",
        },
    )

    assert response.status_code == 302
    incident = Incident.objects.get()
    body = client.get(f"/incidents/{incident.pk}/").content.decode()
    assert "T1" in body
    assert "1h" in body

    stage = incident.stages.get(stage_code="T1")
    client.post(
        f"/incidents/{incident.pk}/stages/{stage.pk}/send/",
        {"channel": "email", "evidence": ""},
        follow=True,
    )
    stage.refresh_from_db()
    assert stage.sent_at is None  # без evidence стадия не закрывается

    reader_client = login(make_user("reader-inc", role="reader"))
    assert (
        reader_client.post(
            "/incidents/new/",
            {
                "kind": "other",
                "detected_at": "2026-10-19T09:00",
                "severity": "low",
                "description": "x",
            },
        ).status_code
        == 403
    )
