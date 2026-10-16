"""Отчёты: состояние контролей, просрочки, покрытие evidence, КЗИ (неделя 11)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.compliance.models import ControlImplementation
from apps.compliance.services import GAP_STATUSES
from apps.core.access import FULL_REGISTRY_ROLES, role_required, user_roles
from apps.evidence.models import EvidenceObject
from apps.kzi.models import Assessment
from apps.obligations.models import ObligationInstance
from apps.registry.models import Asset, System

EXPORT_ROWS_LIMIT = 2000


def _owner_only(user) -> bool:
    roles = user_roles(user)
    return "system_owner" in roles and not roles & FULL_REGISTRY_ROLES


def _gaps(user):
    gaps = (
        ControlImplementation.objects.filter(is_applicable=True, status__in=GAP_STATUSES)
        .select_related("control", "system", "owner_person")
        .order_by("control__code", "system__name")
    )
    if _owner_only(user):
        gaps = gaps.filter(system__owner_person=getattr(user, "person", None))
    return gaps


def _overdue(user):
    overdue = (
        ObligationInstance.objects.filter(status=ObligationInstance.Status.OVERDUE)
        .select_related("template", "owner_person")
        .order_by("due_at")
    )
    if _owner_only(user):
        overdue = overdue.filter(owner_person=getattr(user, "person", None))
    return overdue


@role_required("reports")
def reports_index(request):
    today = timezone.localdate()
    systems = System.objects.order_by("name")
    if _owner_only(request.user):
        systems = systems.filter(owner_person=getattr(request.user, "person", None))
    return render(
        request,
        "reporting/index.html",
        {
            "gaps": _gaps(request.user)[:200],
            "gaps_total": _gaps(request.user).count(),
            "overdue": _overdue(request.user)[:100],
            "overdue_total": _overdue(request.user).count(),
            "evidence_by_kind": EvidenceObject.objects.values("kind").annotate(total=Count("id")),
            "evidence_total": EvidenceObject.objects.count(),
            "evidence_expiring": EvidenceObject.objects.filter(
                valid_until__isnull=False, valid_until__lte=today + timedelta(days=30)
            ).count(),
            "unknown_assets": Asset.objects.filter(
                owner_person__isnull=True, system_components__isnull=True
            ).count(),
            "assessments": Assessment.objects.order_by("-created_at")[:10],
            "systems_total": systems.count(),
        },
    )


@role_required("reports")
def gaps_csv(request):
    lines = ["Код;Контроль;Домен;ИС;Статус;Ответственный;Следующая проверка"]
    for gap in _gaps(request.user)[:EXPORT_ROWS_LIMIT]:
        lines.append(
            ";".join(
                [
                    gap.control.code,
                    gap.control.name.replace(";", ","),
                    gap.control.get_domain_display(),
                    gap.system.name.replace(";", ","),
                    gap.get_status_display(),
                    str(gap.owner_person) if gap.owner_person else "—",
                    gap.next_due_at.strftime("%d.%m.%Y") if gap.next_due_at else "—",
                ]
            )
        )
    response = HttpResponse("\ufeff" + "\n".join(lines), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="gaps.csv"'
    return response


@role_required("reports")
def overdue_csv(request):
    lines = ["Обязательство;Вид;Срок;Ответственный;Уровень эскалации"]
    for item in _overdue(request.user)[:EXPORT_ROWS_LIMIT]:
        lines.append(
            ";".join(
                [
                    item.template.name.replace(";", ","),
                    item.template.get_kind_display(),
                    timezone.localtime(item.due_at).strftime("%d.%m.%Y"),
                    str(item.owner_person) if item.owner_person else "—",
                    str(item.escalation_level),
                ]
            )
        )
    response = HttpResponse("\ufeff" + "\n".join(lines), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="overdue.csv"'
    return response
