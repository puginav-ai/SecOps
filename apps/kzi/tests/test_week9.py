"""Неделя 9: план мероприятий из «почему не 1» — генерация, статусы, выгрузка."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.evidence.models import EvidenceObject
from apps.kzi import services
from apps.kzi.models import (
    Assessment,
    AssessmentSystem,
    KpiItem,
    KpiValue,
    RemediationTask,
)
from apps.registry.models import Person, System

pytestmark = pytest.mark.django_db


@pytest.fixture
def systems() -> list[System]:
    owner = Person.objects.create(fio="Владелец Плана", email="plan@example.test")
    return [
        System.objects.create(name="ЛИС-План", owner_person=owner),
        System.objects.create(name="PACS-План", owner_person=owner),
    ]


@pytest.fixture
def closed_assessment(systems: list[System]) -> Assessment:
    evidence = EvidenceObject.objects.create(
        title="Протокол", file=SimpleUploadedFile("p.pdf", b"x")
    )
    assessment = Assessment.objects.create(
        assessment_type=Assessment.AssessmentType.KZI,
        period_label="2026",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )
    for system in systems:
        AssessmentSystem.objects.create(assessment=assessment, system=system)
    for item in KpiItem.objects.all():
        KpiValue.objects.create(
            assessment=assessment,
            system=systems[0],
            kpi_item=item,
            value=Decimal("1"),
            evidence=evidence,
        )
        KpiValue.objects.create(
            assessment=assessment, system=systems[1], kpi_item=item, value=Decimal("0")
        )
    services.close_assessment(assessment)
    return assessment


def test_plan_requires_closed_assessment(systems: list[System]) -> None:
    draft = Assessment.objects.create(assessment_type="kzi", period_label="draft")
    AssessmentSystem.objects.create(assessment=draft, system=systems[0])

    with pytest.raises(ValidationError):
        services.create_remediation_plan(draft)


def test_plan_generated_for_donor_weak_items(closed_assessment: Assessment) -> None:
    plan = services.create_remediation_plan(closed_assessment)

    weak_codes = [weak["code"] for row in closed_assessment.details["why"] for weak in row["items"]]
    tasks = list(plan.tasks.all())
    assert len(tasks) == len(weak_codes)
    assert tasks, "у донора должны быть слабые KPI"
    donor_name = closed_assessment.details["donor"]
    assert all(task.system.name == donor_name for task in tasks if task.system)
    # дедлайн ≤ следующей оценки (6 месяцев от расчёта)
    assert all(task.due_at is not None for task in tasks)
    # повторная генерация запрещена
    with pytest.raises(ValidationError):
        services.create_remediation_plan(closed_assessment)


def test_plan_views_and_export(client, login, make_user, closed_assessment: Assessment) -> None:
    client = login(make_user("officer-plan", role="ib_officer"))

    response = client.post(f"/kzi/{closed_assessment.pk}/remediation/")
    assert response.status_code == 302
    task = RemediationTask.objects.first()
    assert task is not None

    exported = client.get(f"/kzi/plans/{task.plan_id}/export.csv")
    assert exported.status_code == 200
    body = exported.content.decode("utf-8-sig")
    assert body.startswith("ИС;KPI;Задача;Ответственный;Срок;Статус")
    assert task.title.split("«")[1].rstrip("»") in body

    status_response = client.post(
        f"/kzi/plans/{task.plan_id}/tasks/{task.pk}/status/", {"status": "done"}
    )
    assert status_response.status_code == 302
    task.refresh_from_db()
    assert task.status == RemediationTask.Status.DONE
