"""Отчёты: контроли, просрочки, evidence, КЗИ, 1-страничный отчёт руководству (недели 11–12)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from apps.compliance.models import ControlImplementation
from apps.compliance.services import GAP_STATUSES
from apps.core.access import is_owner_only, role_required
from apps.core.export import csv_response, xlsx_response
from apps.evidence.models import EvidenceObject
from apps.evidence.services import visible_evidence
from apps.incidents.models import Incident
from apps.incidents.services import overdue_stages as incident_overdue_stages
from apps.kzi.models import Assessment, RemediationTask
from apps.obligations.models import ObligationInstance
from apps.registry.models import Asset, System

EXPORT_ROWS_LIMIT = 2000

GAPS_HEADER = ["Код", "Контроль", "Домен", "ИС", "Статус", "Ответственный", "Следующая проверка"]
OVERDUE_HEADER = ["Обязательство", "Вид", "Срок", "Ответственный", "Уровень эскалации"]
EVIDENCE_HEADER = ["Вид evidence", "Количество"]
UNKNOWN_HEADER = ["IP", "MAC", "Имя", "Сегмент", "Обнаружен"]
KZI_HEADER = ["Тип", "Период", "Статус", "Результат", "Вердикт", "Рассчитана"]


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


def _open_incidents(user):
    incidents = Incident.objects.exclude(status=Incident.Status.CLOSED)
    if is_owner_only(user):
        incidents = incidents.filter(system__in=_my_systems(user))
    return incidents


def _open_remediation_tasks(user):
    tasks = RemediationTask.objects.filter(status=RemediationTask.Status.OPEN).select_related(
        "system", "owner_person", "plan"
    )
    if is_owner_only(user):
        tasks = tasks.filter(system__in=_my_systems(user))
    return tasks.order_by("due_at")[:8]


# --- выгрузки: строки ------------------------------------------------------------------


def _gaps_rows(user):
    return [
        [
            gap.control.code,
            gap.control.name,
            gap.control.get_domain_display(),
            gap.system.name,
            gap.get_status_display(),
            str(gap.owner_person) if gap.owner_person else "—",
            gap.next_due_at.strftime("%d.%m.%Y") if gap.next_due_at else "—",
        ]
        for gap in _gaps(user)[:EXPORT_ROWS_LIMIT]
    ]


def _overdue_rows(user):
    return [
        [
            item.template.name,
            item.template.get_kind_display(),
            timezone.localtime(item.due_at).strftime("%d.%m.%Y"),
            str(item.owner_person) if item.owner_person else "—",
            str(item.escalation_level),
        ]
        for item in _overdue(user)[:EXPORT_ROWS_LIMIT]
    ]


def _evidence_rows(user):
    evidence = visible_evidence(user)
    labels = dict(EvidenceObject.Kind.choices)
    return [
        [labels.get(row["kind"], row["kind"]), row["total"]]
        for row in evidence.values("kind").annotate(total=Count("id")).order_by("kind")
    ]


def _unknown_rows(user):
    if is_owner_only(user):
        return []
    assets = Asset.objects.filter(
        owner_person__isnull=True, system_components__isnull=True
    ).select_related("segment")[:EXPORT_ROWS_LIMIT]
    return [
        [
            asset.ip,
            asset.mac or "—",
            asset.hostname or "—",
            asset.segment.name if asset.segment else "—",
            asset.first_seen_at.strftime("%d.%m.%Y %H:%M"),
        ]
        for asset in assets
    ]


def _kzi_rows(user):
    return [
        [
            assessment.get_assessment_type_display(),
            assessment.period_label or "—",
            assessment.get_status_display(),
            str(assessment.result_value) if assessment.result_value is not None else "—",
            assessment.verdict or "—",
            assessment.assessed_at.strftime("%d.%m.%Y %H:%M") if assessment.assessed_at else "—",
        ]
        for assessment in _scoped_assessments(user)[:EXPORT_ROWS_LIMIT]
    ]


# --- страницы ---------------------------------------------------------------------------


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
def management_report(request):
    """Одностраничный отчёт руководству: цифры, риски, план, КЗИ (SDD §5.9)."""
    today = timezone.localdate()
    owner_only = is_owner_only(request.user)
    systems = _my_systems(request.user) if owner_only else System.objects.all()
    evidence = visible_evidence(request.user)
    if owner_only:
        my_assets = Asset.objects.filter(system_components__system__in=systems).distinct()
    else:
        my_assets = Asset.objects.all()
    return render(
        request,
        "reporting/management.html",
        {
            "generated_at": timezone.localtime(),
            "assets_total": my_assets.count(),
            "assets_active": my_assets.filter(miss_count__lt=3).count(),
            "systems_total": systems.count(),
            "gaps_total": _gaps(request.user).count(),
            "incidents_open": _open_incidents(request.user).count(),
            "incident_overdue_count": incident_overdue_stages()
            .filter(incident__in=_open_incidents(request.user))
            .count(),
            "obligations_overdue": _overdue(request.user).count(),
            "overdue_top": _overdue(request.user)[:5],
            "incident_overdue_top": list(
                incident_overdue_stages()
                .filter(incident__in=_open_incidents(request.user))
                .order_by("deadline_at")[:5]
            ),
            "evidence_expiring_total": evidence.filter(
                valid_until__isnull=False, valid_until__lte=today + timedelta(days=30)
            ).count(),
            "evidence_expiring": evidence.filter(
                valid_until__isnull=False, valid_until__lte=today + timedelta(days=30)
            ).order_by("valid_until")[:5],
            "unknown_assets": (
                None
                if owner_only
                else Asset.objects.filter(
                    owner_person__isnull=True, system_components__isnull=True
                ).count()
            ),
            "plan_tasks": _open_remediation_tasks(request.user),
            "last_assessment": _scoped_assessments(request.user)
            .filter(status=Assessment.Status.CLOSED)
            .order_by("-assessed_at")
            .first(),
        },
    )


# --- CSV -------------------------------------------------------------------------------


@role_required("reports")
def gaps_csv(request):
    return csv_response("gaps.csv", GAPS_HEADER, _gaps_rows(request.user))


@role_required("reports")
def overdue_csv(request):
    return csv_response("overdue.csv", OVERDUE_HEADER, _overdue_rows(request.user))


# --- XLSX ------------------------------------------------------------------------------


@role_required("reports")
def gaps_xlsx(request):
    return xlsx_response("gaps.xlsx", GAPS_HEADER, _gaps_rows(request.user))


@role_required("reports")
def overdue_xlsx(request):
    return xlsx_response("overdue.xlsx", OVERDUE_HEADER, _overdue_rows(request.user))


@role_required("reports")
def evidence_xlsx(request):
    return xlsx_response("evidence.xlsx", EVIDENCE_HEADER, _evidence_rows(request.user))


@role_required("reports")
def unknown_xlsx(request):
    return xlsx_response("unknown-assets.xlsx", UNKNOWN_HEADER, _unknown_rows(request.user))


@role_required("reports")
def kzi_xlsx(request):
    return xlsx_response("kzi.xlsx", KZI_HEADER, _kzi_rows(request.user))
