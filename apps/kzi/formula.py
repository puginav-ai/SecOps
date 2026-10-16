"""Формула КЗИ/ПЗИ (SDD §3.4) — изолированный модуль.

Формула по умолчанию; при появлении утверждённой методики заменяется здесь,
остальные модули не меняются. Все вычисления — Decimal, округление до 4 знаков.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class ItemValue:
    """Значение KPI: вес, значение (None = нет данных), максимум, обязательность."""

    weight: Decimal
    value: Decimal | None
    max_value: Decimal
    is_mandatory: bool = False


def group_score(items: list[ItemValue], cap: Decimal | None = None) -> Decimal:
    """Оценка группы: Σ(weight·value)/Σ(weight·max); cap ограничивает сверху.

    Необязательные NULL считаются 0 («не подтверждено»); обязательные NULL
    не должны доходить сюда — блокируются при закрытии.
    """
    denominator = sum((item.weight * item.max_value for item in items), Decimal(0))
    if denominator <= 0:
        return Decimal(0)
    numerator = sum(((item.value or Decimal(0)) * item.weight for item in items), Decimal(0))
    score = numerator / denominator
    if cap is not None:
        score = min(score, cap)
    return score.quantize(QUANT, rounding=ROUND_HALF_UP)


def system_score(group_scores: list[tuple[Decimal, Decimal]]) -> Decimal:
    """Оценка системы: Σ вес_группы · оценка_группы (без учёта капов — они уже в группах)."""
    total = sum((weight * score for weight, score in group_scores), Decimal(0))
    return total.quantize(QUANT, rounding=ROUND_HALF_UP)


def final_score(system_scores: dict[str, Decimal]) -> tuple[Decimal, str]:
    """Итог = минимум по скоупу; возвращает (значение, система-«донор» минимума)."""
    if not system_scores:
        return Decimal(0), ""
    donor, value = min(system_scores.items(), key=lambda item: item[1])
    return value, donor


def verdict(value: Decimal, high: Decimal, medium: Decimal) -> str:
    """Вердикт по порогам (default: ≥0.95 высокий, ≥0.80 средний, иначе низкий)."""
    if value >= high:
        return "высокий"
    if value >= medium:
        return "средний"
    return "низкий"


def explanation_rows(
    group_weights: dict[str, Decimal], group_values: dict[str, Decimal]
) -> list[dict]:
    """«Почему не 1»: вклад групп в отставание weight·(1−score), по убыванию."""
    rows = [
        {
            "group": code,
            "weight": group_weights.get(code, Decimal(0)),
            "score": score,
            "gap": (group_weights.get(code, Decimal(0)) * (Decimal(1) - score)).quantize(
                QUANT, rounding=ROUND_HALF_UP
            ),
        }
        for code, score in group_values.items()
    ]
    return sorted(rows, key=lambda row: row["gap"], reverse=True)
