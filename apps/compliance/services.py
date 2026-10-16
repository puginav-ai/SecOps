"""Сервисные правила контролей (SDD §3.2, §5.3): матрица и статусные переходы."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.compliance.models import ControlImplementation
from apps.core.access import user_roles

# «Применимо, но не внедрено / не подтверждено» — фильтр пробелов (SDD §5.3)
GAP_STATUSES = {
    ControlImplementation.Status.PLANNED,
    ControlImplementation.Status.NON_COMPLIANT,
    ControlImplementation.Status.IMPLEMENTED,
}


def ensure_implementations(controls, systems) -> int:
    """Достраивает матрицу «ИС × контроль».

    Стартовое состояние: «применимо + запланировано» — строка сразу видна
    в списке пробелов и требует осознанной работы (ADR недели 4).
    """
    existing = set(
        ControlImplementation.objects.filter(control__in=controls, system__in=systems).values_list(
            "control_id", "system_id"
        )
    )
    created = 0
    for control in controls:
        for system in systems:
            if (control.pk, system.pk) in existing:
                continue
            ControlImplementation.objects.create(
                control=control,
                system=system,
                is_applicable=True,
                status=ControlImplementation.Status.PLANNED,
            )
            created += 1
    return created


def validate_status(implementation: ControlImplementation, new_status: str, user) -> None:
    """Правила переходов (SDD §3.2). Бросает ValidationError при нарушении."""
    valid = {choice for choice, _ in ControlImplementation.Status.choices}
    if new_status not in valid:
        raise ValidationError(f"Неизвестный статус: {new_status}")

    if new_status == ControlImplementation.Status.VERIFIED and implementation.last_test_at is None:
        raise ValidationError("Нельзя подтвердить контроль без прогона проверки")

    if new_status == ControlImplementation.Status.NA and implementation.is_applicable:
        raise ValidationError("Статус «не применимо» требует отметки о неприменимости")

    if new_status == ControlImplementation.Status.EXCEPTION:
        roles = user_roles(user)
        is_admin = bool(getattr(user, "is_superuser", False)) or "ib_admin" in roles
        if not is_admin:
            raise ValidationError("Исключение может выставить только ИБ-админ")
        if not implementation.exception_note or not implementation.exception_review_at:
            raise ValidationError("Для исключения нужны обоснование и срок пересмотра")
        if implementation.exception_evidence_id is None:
            raise ValidationError("Для исключения нужен evidence решения руководства (SDD §4)")


def set_status(implementation: ControlImplementation, new_status: str, user) -> None:
    """Переход статуса с правилами и сохранением."""
    validate_status(implementation, new_status, user)
    implementation.status = new_status
    fields = ["status"]
    if new_status == ControlImplementation.Status.EXCEPTION:
        implementation.exception_approved_at = timezone.now()
        fields.append("exception_approved_at")
    implementation.save(update_fields=fields)
