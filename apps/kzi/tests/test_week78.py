"""Недели 7–8: формула КЗИ, правила закрытия, снапшот, экраны оценки."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.evidence.models import EvidenceObject
from apps.kzi import formula, services
from apps.kzi.formula import ItemValue
from apps.kzi.models import (
    Assessment,
    AssessmentPenalty,
    AssessmentSystem,
    KpiGroup,
    KpiItem,
    KpiValue,
)
from apps.registry.models import Person, System

pytestmark = pytest.mark.django_db


# --- формула (чистые функции) ---------------------------------------------------------


def decimal(value: str) -> Decimal:
    return Decimal(value)


def test_group_score_equal_values() -> None:
    items = [
        ItemValue(weight=decimal("1"), value=decimal("1"), max_value=decimal("1")),
        ItemValue(weight=decimal("1"), value=decimal("1"), max_value=decimal("1")),
    ]

    assert formula.group_score(items) == decimal("1.0000")


def test_group_score_optional_null_counts_as_zero() -> None:
    items = [
        ItemValue(weight=decimal("1"), value=decimal("1"), max_value=decimal("1")),
        ItemValue(weight=decimal("1"), value=None, max_value=decimal("1"), is_mandatory=False),
    ]

    assert formula.group_score(items) == decimal("0.5000")


def test_group_score_respects_cap() -> None:
    items = [ItemValue(weight=decimal("1"), value=decimal("1"), max_value=decimal("1"))]

    assert formula.group_score(items, cap=decimal("0.4000")) == decimal("0.4000")


def test_final_score_picks_minimum_and_donor() -> None:
    final, donor = formula.final_score({"ЛИС": decimal("0.9000"), "PACS": decimal("0.7000")})

    assert final == decimal("0.7000")
    assert donor == "PACS"


def test_explanation_sorted_by_gap() -> None:
    rows = formula.explanation_rows(
        {"ACC": decimal("0.3"), "ORG": decimal("0.2")},
        {"ACC": decimal("0.5"), "ORG": decimal("1")},
    )

    assert rows[0]["group"] == "ACC"
    assert rows[0]["gap"] == decimal("0.1500")


def test_verdict_thresholds() -> None:
    assert formula.verdict(decimal("0.96"), decimal("0.95"), decimal("0.80")) == "высокий"
    assert formula.verdict(decimal("0.85"), decimal("0.95"), decimal("0.80")) == "средний"
    assert formula.verdict(decimal("0.5"), decimal("0.95"), decimal("0.80")) == "низкий"


# --- сервис: правила закрытия и снапшот -----------------------------------------------


@pytest.fixture
def systems() -> list[System]:
    owner = Person.objects.create(fio="Владелец КЗИ Тестовый")
    return [
        System.objects.create(name="ЛИС-КЗИ", owner_person=owner),
        System.objects.create(name="PACS-КЗИ", owner_person=owner),
    ]


@pytest.fixture
def assessment(systems: list[System]) -> Assessment:
    instance = Assessment.objects.create(
        assessment_type=Assessment.AssessmentType.KZI,
        period_label="2026",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )
    for system in systems:
        AssessmentSystem.objects.create(assessment=instance, system=system)
    return instance


@pytest.fixture
def evidence() -> EvidenceObject:
    return EvidenceObject.objects.create(
        title="Протокол проверки", file=SimpleUploadedFile("kzi.pdf", b"x")
    )


def fill(
    assessment: Assessment, system: System, value: str, evidence: EvidenceObject | None
) -> None:
    for item in KpiItem.objects.all():
        KpiValue.objects.create(
            assessment=assessment,
            system=system,
            kpi_item=item,
            value=decimal(value),
            evidence=evidence if decimal(value) > 0 else None,
        )


def test_close_blocked_by_mandatory_null(assessment: Assessment) -> None:
    with pytest.raises(ValidationError):
        services.close_assessment(assessment)

    assessment.refresh_from_db()
    assert assessment.status == Assessment.Status.INCOMPLETE
    assert services.missing_mandatory(assessment)


def test_close_blocked_by_value_without_evidence(
    assessment: Assessment, systems: list[System]
) -> None:
    for system in systems:
        fill(assessment, system, "1", evidence=None)

    with pytest.raises(ValidationError) as excinfo:
        services.close_assessment(assessment)

    assert "evidence" in str(excinfo.value)


def test_close_computes_snapshot_and_is_reproducible(
    assessment: Assessment, systems: list[System], evidence: EvidenceObject
) -> None:
    fill(assessment, systems[0], "1", evidence)
    fill(assessment, systems[1], "0", None)  # 0 без evidence разрешён

    snapshot = services.close_assessment(assessment)

    assert snapshot["final"] == "0.0000"
    assert snapshot["donor"] == systems[1].name
    assert snapshot["verdict"] == "низкий"
    assert snapshot["why"][0]["score"] == "0.0000"

    assessment.refresh_from_db()
    assert assessment.status == Assessment.Status.CLOSED
    assert assessment.details["systems"] == snapshot["systems"]  # снапшот воспроизводим
    assert services.compute_snapshot(assessment)["systems"] == snapshot["systems"]


def test_penalty_cap_limits_group(
    assessment: Assessment, systems: list[System], evidence: EvidenceObject
) -> None:
    for system in systems:
        fill(assessment, system, "1", evidence)
    acc = KpiGroup.objects.get(code="ACC")
    AssessmentPenalty.objects.create(
        assessment=assessment,
        kpi_group=acc,
        window_start=date(2026, 1, 1),
        window_end=date(2026, 12, 31),
        reason="Тестовый кап",
        cap_value=decimal("0.5"),
    )

    snapshot = services.close_assessment(assessment)

    assert snapshot["systems"][systems[0].name]["groups"]["ACC"] == "0.5000"
    assert Decimal(snapshot["final"]) < Decimal("1")


# --- экран -----------------------------------------------------------------------------


def test_assessment_views_flow(client, login, make_user, systems: list[System]) -> None:
    client = login(make_user("officer-kzi", role="ib_officer"))

    response = client.post(
        "/kzi/new/",
        {
            "assessment_type": "kzi",
            "period_label": "2026",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "systems": [system.pk for system in systems],
        },
    )

    assert response.status_code == 302
    assessment = Assessment.objects.get()

    detail = client.get(f"/kzi/{assessment.pk}/")
    assert detail.status_code == 200
    body = detail.content.decode()
    assert systems[0].name in body
    assert "Расчёт" in body
