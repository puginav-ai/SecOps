"""E2E пилотных потоков (неделя 12): полный цикл через HTTP-стек консоли.

Потоки: контроль → проверка с evidence → подтверждено; обязательство → закрытие с evidence;
инцидент → таймеры → отправка с evidence → закрытие; КЗИ → оценка → закрытие → план → выгрузка.
Playwright-прогон в браузере — отдельный шаг CI (после выделения ресурсов); здесь —
сквозные сценарии по реальному стеку Django (формы, права, сервисы).
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.compliance.models import Control, ControlImplementation
from apps.evidence.models import EvidenceObject
from apps.incidents.models import Incident
from apps.kzi.models import Assessment, KpiItem
from apps.obligations.models import ObligationInstance, ObligationTemplate
from apps.registry.models import Asset, Person, System

pytestmark = pytest.mark.django_db


@pytest.fixture
def officer(client, login, make_user):
    return login(make_user("pilot-officer", role="ib_officer"))


@pytest.fixture
def pilot_system() -> System:
    owner = Person.objects.create(fio="Владелец Пилота", email="pilot@example.test")
    return System.objects.create(name="ЛИС-Пилот", owner_person=owner, kii_scope="yes")


def upload_evidence(client, title: str = "Протокол проверки ЛИС") -> EvidenceObject:
    response = client.post(
        "/evidence/upload/",
        {
            "title": title,
            "kind": "act",
            "issued_at": "2026-10-19",
            "valid_until": "2027-10-19",
            "confidentiality": "internal",
            "letter_direction": "",
            "letter_number": "",
            "letter_date": "",
            "correspondent": "",
            "reply_due_at": "",
            "reply_status": "",
            "file": SimpleUploadedFile(
                "protocol.pdf", b"pilot-evidence", content_type="application/pdf"
            ),
        },
    )
    assert response.status_code == 302
    return EvidenceObject.objects.get(title=title)


def test_control_flow_to_verified(officer, pilot_system: System) -> None:
    evidence = upload_evidence(officer, "Экспорт антивируса")

    officer.get("/compliance/")  # матрица достраивается
    implementation = ControlImplementation.objects.get(
        control=Control.objects.get(code="ANTIVIR"), system=pilot_system
    )

    response = officer.post(
        f"/compliance/implementations/{implementation.pk}/test/",
        {
            "test": implementation.control.tests.first().pk,
            "run_at": "2026-10-19T10:00",
            "result": "pass",
            "evidence": evidence.pk,
            "notes": "Пилотная проверка",
        },
    )
    assert response.status_code == 302

    response = officer.post(
        f"/compliance/implementations/{implementation.pk}/edit/",
        {
            "is_applicable": "on",
            "applicability_reason": "Применимо (пилот)",
            "status": ControlImplementation.Status.VERIFIED,
            "owner_person": "",
            "exception_note": "",
            "exception_evidence": "",
            "exception_review_at": "",
        },
    )
    assert response.status_code == 302

    implementation.refresh_from_db()
    assert implementation.status == ControlImplementation.Status.VERIFIED
    assert implementation.last_test_at is not None
    assert implementation.next_due_at is not None  # пересчитан по периодичности


def test_obligation_close_with_evidence(officer, pilot_system: System) -> None:
    template = ObligationTemplate.objects.create(
        kind=ObligationTemplate.Kind.KZI,
        name="Пилот: оценка КЗИ",
        requires_closing_evidence=True,
    )
    instance = ObligationInstance.objects.create(
        template=template, due_at=timezone.now(), owner_person=pilot_system.owner_person
    )
    evidence = upload_evidence(officer, "Протокол КЗИ (пилот)")

    response = officer.post(f"/obligations/{instance.pk}/close/", {"evidence": evidence.pk})

    assert response.status_code == 302
    instance.refresh_from_db()
    assert instance.status == ObligationInstance.Status.DONE
    assert instance.closure_evidence_id == evidence.pk


def test_incident_flow_timers_and_closure(officer, pilot_system: System) -> None:
    response = officer.post(
        "/incidents/new/",
        {
            "kind": "kii",
            "detected_at": "2026-10-19T09:00",
            "system": pilot_system.pk,
            "severity": "high",
            "description": "Пилотный инцидент КИИ",
        },
    )
    assert response.status_code == 302
    incident = Incident.objects.get()
    assert incident.stages.count() >= 3  # 1h, T1, T2, regulator_24

    evidence = upload_evidence(officer, "Письмо в ФСТЭК (пилот)")
    for stage in incident.stages.all():
        response = officer.post(
            f"/incidents/{incident.pk}/stages/{stage.pk}/send/",
            {"evidence": evidence.pk, "channel": "email"},
        )
        assert response.status_code == 302
    assert incident.stages.filter(sent_at__isnull=True).count() == 0

    response = officer.post(f"/incidents/{incident.pk}/close/")
    assert response.status_code == 302
    incident.refresh_from_db()
    assert incident.status == Incident.Status.CLOSED


def test_kzi_assessment_to_plan(officer, pilot_system: System) -> None:
    response = officer.post(
        "/kzi/new/",
        {
            "assessment_type": "kzi",
            "period_label": "Пилот 2026",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "systems": [pilot_system.pk],
        },
    )
    assert response.status_code == 302
    assessment = Assessment.objects.get()

    evidence = upload_evidence(officer, "Подтверждение KPI (пилот)")
    payload = {}
    for item in KpiItem.objects.all():
        payload[f"value-{pilot_system.pk}-{item.pk}"] = "1"
        payload[f"evidence-{pilot_system.pk}-{item.pk}"] = str(evidence.pk)
    response = officer.post(f"/kzi/{assessment.pk}/values/", payload)
    assert response.status_code == 302

    response = officer.post(f"/kzi/{assessment.pk}/close/")
    assert response.status_code == 302
    assessment.refresh_from_db()
    assert assessment.status == Assessment.Status.CLOSED
    assert str(assessment.result_value) == "1.0000"

    # Без отставаний план создаётся пустым — это корректно; проверим сам механизм выгрузки
    response = officer.post(f"/kzi/{assessment.pk}/remediation/")
    assert response.status_code == 302


def test_unknown_assets_shrink_after_linking(officer, pilot_system: System) -> None:
    asset = Asset.objects.create(
        ip="10.60.9.99", hostname="pilot-unknown", last_seen_at=timezone.now()
    )
    body = officer.get("/registry/assets/unknown/").content.decode()
    assert "pilot-unknown" in body

    response = officer.post(
        f"/registry/systems/{pilot_system.pk}/components/add/",
        {"asset": asset.pk, "role": "server", "note": "пилот"},
    )
    assert response.status_code == 302
    body = officer.get("/registry/assets/unknown/").content.decode()
    assert "pilot-unknown" not in body
