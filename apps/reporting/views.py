"""Отчёты: состояние контролей, просрочки, покрытие evidence, КЗИ (неделя 11)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from apps.compliance.models import ControlImplementation
from apps.compliance.services import GAP_STATUSES
from apps.core.access import is_owner_only, role_required
from apps.core.export import csv_response
from apps.evidence.services import visible_evidence
from apps.kzi.models import Assessment
from apps.obligations.models import ObligationInstance
from apps.registry.models import Asset, System

EXPORT_ROWS_LIMIT = 2000


def _person(user):
    return getattr(user, "person", None)


def _my_systems(user):
    person = _person(user)
    if person is None:
        return System.objects.none()
    return System.objects.filter(owner_person=person)


def _gaps(user):
    gaps = (
        ControlImplementation.objects.filter(is_applicable=True, status__in=GAP_STATUSES)
        .select_related("control", "system", "owner_person")
        .order_by("control__code", "system__name")
    )
    if is_owner_only(user):
        gaps = gaps.filter(system__in=_my_systems(user))
    return gaps


def _overdue(user):
    overdue = (
        ObligationInstance.objects.filter(status=ObligationInstance.Status.OVERDUE)
        .select_related("template", "owner_person")
        .order_by("due_at")
    )
    if is_owner_only(user):
        person = _person(user)
        overdue = overdue.filter(owner_person=person) if person else overdue.none()
    return overdue


def _scoped_assessments(user):
    assessments = Assessment.objects.order_by("-created_at")
    if is_owner_only(user):
        assessments = assessments.filter(scope__system__in=_my_systems(user)).distinct()
    return assessments


@role_required("reports")
def reports_index(request):
    today = timezone.localdate()
    owner_only = is_owner_only(request.user)
    evidence = visible_evidence(request.user)
    return render(
        request,
        "reporting/index.html",
        {
            "gaps": _gaps(request.user)[:200],
            "gaps_total": _gaps(request.user).count(),
            "overdue": _overdue(request.user)[:100],
            "overdue_total": _overdue(request.user).count(),
            "evidence_by_kind": evidence.values("kind").annotate(total=Count("id")),
            "evidence_total": evidence.count(),
            "evidence_expiring": evidence.filter(
                valid_until__isnull=False, valid_until__lte=today + timedelta(days=30)
            ).count(),
            "unknown_assets": (
                None
                if owner_only
                else Asset.objects.filter(
                    owner_person__isnull=True, system_components__isnull=True
                ).count()
            ),
            "assessments": _scoped_assessments(request.user)[:10],
            "systems_total": (
                _my_systems(request.user) if owner_only else System.objects.all()
            ).count(),
        },
    )


@role_required("reports")
def gaps_csv(request):
    rows = [
        [
            gap.control.code,
            gap.control.name,
            gap.control.get_domain_display(),
            gap.system.name,
            gap.get_status_display(),
            str(gap.owner_person) if gap.owner_person else "—",
            gap.next_due_at.strftime("%d.%m.%Y") if gap.next_due_at else "—",
        ]
        for gap in _gaps(request.user)[:EXPORT_ROWS_LIMIT]
    ]
    header = ["Код", "Контроль", "Домен", "ИС", "Статус", "Ответственный", "Следующая проверка"]
    return csv_response("gaps.csv", header, rows)


@role_required("reports")
def overdue_csv(request):
    rows = [
        [
            item.template.name,
            item.template.get_kind_display(),
            timezone.localtime(item.due_at).strftime("%d.%m.%Y"),
            str(item.owner_person) if item.owner_person else "—",
            str(item.escalation_level),
        ]
        for item in _overdue(request.user)[:EXPORT_ROWS_LIMIT]
    ]
    header = ["Обязательство", "Вид", "Срок", "Ответственный", "Уровень эскалации"]
    return csv_response("overdue.csv", header, rows)
