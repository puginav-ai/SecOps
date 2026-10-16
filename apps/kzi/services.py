"""Сервисы КЗИ: валидация закрытия и расчёт со снапшотом (SDD §3.4)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.kzi import formula
from apps.kzi.formula import ItemValue
from apps.kzi.models import Assessment, KpiGroup, KpiItem, KpiValue


def missing_mandatory(assessment: Assessment) -> list[tuple]:
    """Обязательные KPI без значения (NULL) в скоупе — блокируют закрытие."""
    rows: list[tuple] = []
    mandatory = list(KpiItem.objects.filter(is_mandatory=True))
    for link in assessment.scope.select_related("system"):
        system = link.system
        for item in mandatory:
            value = KpiValue.objects.filter(
                assessment=assessment, system=system, kpi_item=item
            ).first()
            if value is None or value.value is None:
                rows.append((system, item))
    return rows


def values_without_evidence(assessment: Assessment) -> list[KpiValue]:
    """Значения >0 без evidence — запрещены (0 без evidence допустим)."""
    return list(
        assessment.values.filter(value__gt=0, evidence__isnull=True).select_related(
            "system", "kpi_item"
        )
    )


def compute_snapshot(assessment: Assessment) -> dict:
    """Расчёт по формуле SDD §3.4 со всеми промежуточными значениями (JSON-совместимо)."""
    groups = list(KpiGroup.objects.order_by("sort"))
    items_by_group = {group.code: list(group.items.order_by("sort", "code")) for group in groups}
    penalties = {penalty.kpi_group_id: penalty for penalty in assessment.penalties.all()}
    values = {(value.system_id, value.kpi_item_id): value for value in assessment.values.all()}
    systems = [link.system for link in assessment.scope.select_related("system")]

    def cap_for(group: KpiGroup) -> Decimal | None:
        penalty = penalties.get(group.pk)
        if penalty is None:
            return None
        start, end = assessment.period_start, assessment.period_end
        if start and end and (penalty.window_start > end or penalty.window_end < start):
            return None
        return penalty.cap_value

    system_scores: dict[str, Decimal] = {}
    per_system_groups: dict[str, dict[str, Decimal]] = {}
    by_name = {system.name: system for system in systems}
    for system in systems:
        group_scores: dict[str, Decimal] = {}
        for group in groups:
            item_values = []
            for item in items_by_group[group.code]:
                stored = values.get((system.pk, item.pk))
                item_values.append(
                    ItemValue(
                        weight=item.weight,
                        value=stored.value if stored else None,
                        max_value=item.max_value,
                        is_mandatory=item.is_mandatory,
                    )
                )
            group_scores[group.code] = formula.group_score(item_values, cap=cap_for(group))
        per_system_groups[system.name] = group_scores
        system_scores[system.name] = formula.system_score(
            [(group.weight_rj, group_scores[group.code]) for group in groups]
        )

    final, donor = formula.final_score(system_scores)
    why: list[dict] = []
    if donor:
        donor_system = by_name[donor]
        rows = formula.explanation_rows(
            {group.code: group.weight_rj for group in groups}, per_system_groups[donor]
        )
        for row in rows:
            if row["gap"] <= 0:
                continue
            weak_items = []
            for item in items_by_group[row["group"]]:
                stored = values.get((donor_system.pk, item.pk))
                current = stored.value if stored else None
                if current is None or current < item.max_value:
                    weak_items.append(
                        {
                            "code": item.code,
                            "name": item.name,
                            "value": str(current) if current is not None else None,
                            "evidence_id": stored.evidence_id if stored else None,
                        }
                    )
            why.append(
                {
                    "group": row["group"],
                    "weight": str(row["weight"]),
                    "gap": str(row["gap"]),
                    "score": str(row["score"]),
                    "items": weak_items,
                }
            )

    return {
        "computed_at": timezone.now().isoformat(),
        "groups": [
            {
                "code": group.code,
                "name": group.name,
                "weight": str(group.weight_rj),
                "cap": str(cap_for(group)) if cap_for(group) is not None else None,
            }
            for group in groups
        ],
        "systems": {
            name: {
                "groups": {code: str(score) for code, score in group_scores.items()},
                "score": str(system_scores[name]),
            }
            for name, group_scores in per_system_groups.items()
        },
        "final": str(final),
        "donor": donor,
        "verdict": formula.verdict(final, settings.KZI_VERDICT_HIGH, settings.KZI_VERDICT_MEDIUM),
        "why": why,
    }


def close_assessment(assessment: Assessment) -> dict:
    """Закрытие: правила полноты → расчёт → снапшот в `details`. Возвращает снапшот."""
    gaps = missing_mandatory(assessment)
    if gaps:
        assessment.status = Assessment.Status.INCOMPLETE
        assessment.save(update_fields=["status"])
        listing = ", ".join(f"{system.name}: {item.code}" for system, item in gaps[:5])
        raise ValidationError(f"Обязательные KPI без значения: {listing}")

    no_evidence = values_without_evidence(assessment)
    if no_evidence:
        assessment.status = Assessment.Status.INCOMPLETE
        assessment.save(update_fields=["status"])
        listing = ", ".join(
            f"{value.system.name}: {value.kpi_item.code}" for value in no_evidence[:5]
        )
        raise ValidationError(f"Значения больше нуля требуют evidence: {listing}")

    snapshot = compute_snapshot(assessment)
    assessment.status = Assessment.Status.CLOSED
    assessment.assessed_at = timezone.now()
    assessment.result_value = Decimal(snapshot["final"])
    assessment.verdict = snapshot["verdict"]
    assessment.details = snapshot
    assessment.save(update_fields=["status", "assessed_at", "result_value", "verdict", "details"])
    return snapshot


def parse_value(raw: str) -> Decimal | None:
    """Разбор значения из формы: пусто → NULL, иначе Decimal (ошибка → ValidationError)."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise ValidationError(f"Значение «{raw}» — не число") from exc
