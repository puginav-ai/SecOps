"""UI ядра: дашборд по ролям со сводкой (неделя 11)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.compliance.models import ControlImplementation
from apps.compliance.services import GAP_STATUSES
from apps.core.access import (
    FULL_REGISTRY_ROLES,
    MODULES,
    ROLE_TITLES,
    user_modules,
    user_roles,
)
from apps.discovery.services import MISS_THRESHOLD
from apps.evidence.models import EvidenceObject
from apps.kzi.models import Assessment
from apps.obligations.models import ObligationInstance
from apps.registry.models import Asset, System

MODULE_URLS: dict[str, str] = {
    "registry": "/registry/",
    "discovery": "/registry/assets/",
    "compliance": "/compliance/",
    "evidence": "/evidence/",
    "obligations": "/obligations/",
    "kzi": "/kzi/",
    "reports": "/reports/",
    "admin": "/admin/",
}


def _summary(user) -> dict:
    """Сводка по контуру; владелец ИС видит только свои системы и обязательства."""
    roles = user_roles(user)
    owner_only = "system_owner" in roles and not roles & FULL_REGISTRY_ROLES
    systems = System.objects.all()
    obligations = ObligationInstance.objects.all()
    gaps = ControlImplementation.objects.filter(is_applicable=True, status__in=GAP_STATUSES)
    if owner_only:
        person = getattr(user, "person", None)
        systems = systems.filter(owner_person=person)
        obligations = obligations.filter(owner_person=person)
        gaps = gaps.filter(system__in=systems)

    today = timezone.localdate()
    soon_limit = timezone.now() + timedelta(days=30)
    return {
        "assets_total": Asset.objects.count(),
        "assets_active": Asset.objects.filter(miss_count__lt=MISS_THRESHOLD).count(),
        "unknown_assets": Asset.objects.filter(
            owner_person__isnull=True, system_components__isnull=True
        ).count(),
        "systems_count": systems.count(),
        "gaps_count": gaps.count(),
        "obligations_overdue": obligations.filter(status=ObligationInstance.Status.OVERDUE).count(),
        "obligations_soon": obligations.filter(status=ObligationInstance.Status.DUE_SOON).count(),
        "overdue_top": obligations.filter(status=ObligationInstance.Status.OVERDUE)
        .select_related("template", "owner_person")
        .order_by("due_at")[:5],
        "evidence_expiring": EvidenceObject.objects.filter(
            valid_until__isnull=False, valid_until__lte=today + timedelta(days=30)
        ).count(),
        "assessment_soon_limit": soon_limit,
        "last_assessment": Assessment.objects.filter(status=Assessment.Status.CLOSED)
        .order_by("-assessed_at")
        .first(),
    }


@login_required
def dashboard(request):
    modules = [
        {
            "code": code,
            "title": MODULES[code],
            "access": access,
            "url": MODULE_URLS.get(code, ""),
        }
        for code, access in user_modules(request.user)
    ]
    roles = sorted(ROLE_TITLES.get(role, role) for role in user_roles(request.user))
    return render(
        request,
        "core/dashboard.html",
        {"modules": modules, "roles": roles, "summary": _summary(request.user)},
    )
