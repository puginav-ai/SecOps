"""UI контролей: матрица «ИС × контроль», каталог, правка и прогон проверок (неделя 4)."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.compliance import services
from apps.compliance.forms import ControlImplementationForm, TestRunForm
from apps.compliance.models import Control, ControlImplementation, NormAct
from apps.core.access import FULL_REGISTRY_ROLES, module_access, role_required, user_roles
from apps.registry.models import System


def _visible_systems(request):
    """Тот же принцип, что в реестре: владелец ИС видит только свои системы (SDD §4)."""
    systems = System.objects.order_by("name")
    roles = user_roles(request.user)
    if "system_owner" in roles and not roles & FULL_REGISTRY_ROLES:
        systems = systems.filter(owner_person__user=request.user)
    return systems


@role_required("compliance")
def matrix(request):
    """Матрица «ИС × контроль»; ?gap=1 — только «применимо, но не внедрено/не подтверждено»."""
    systems = list(_visible_systems(request))
    controls = list(Control.objects.order_by("code"))
    services.ensure_implementations(controls, systems)

    implementations = {
        (impl.control_id, impl.system_id): impl
        for impl in ControlImplementation.objects.filter(
            control__in=controls, system__in=systems
        ).select_related("owner_person")
    }

    gap_only = request.GET.get("gap") == "1"
    if gap_only:
        controls = [control for control in controls if _has_gap(control, systems, implementations)]

    rows = [
        {
            "control": control,
            "cells": [
                {"system": system, "impl": implementations.get((control.pk, system.pk))}
                for system in systems
            ],
        }
        for control in controls
    ]
    return render(
        request,
        "compliance/matrix.html",
        {
            "rows": rows,
            "systems": systems,
            "gap_only": gap_only,
            "can_edit": module_access(request.user, "compliance") == "rw",
        },
    )


def _has_gap(control, systems: list, implementations: dict) -> bool:
    for system in systems:
        impl = implementations.get((control.pk, system.pk))
        if impl and impl.is_applicable and impl.status in services.GAP_STATUSES:
            return True
    return False


@role_required("compliance")
def catalog(request):
    """Каталог: НПА → требования → контроли (топ-15) с проверками."""
    acts = NormAct.objects.prefetch_related("requirements__control_links__control").order_by("name")
    controls = Control.objects.prefetch_related("tests").order_by("code")
    return render(request, "compliance/catalog.html", {"acts": acts, "controls": controls})


@role_required("compliance", "rw")
def implementation_edit(request, pk: int):
    implementation = get_object_or_404(
        ControlImplementation.objects.select_related("control", "system"), pk=pk
    )
    form = ControlImplementationForm(request.POST or None, instance=implementation)
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        try:
            services.validate_status(candidate, candidate.status, request.user)
        except ValidationError as exc:
            form.add_error("status", exc)
        else:
            candidate.save()
            if (
                candidate.status == ControlImplementation.Status.EXCEPTION
                and candidate.exception_approved_at is None
            ):
                candidate.exception_approved_at = timezone.now()
                candidate.save(update_fields=["exception_approved_at"])
            messages.success(
                request, f"{candidate.control.code}: статус — {candidate.get_status_display()}"
            )
            return redirect("compliance:matrix")
    return render(
        request,
        "compliance/implementation_form.html",
        {"form": form, "implementation": implementation},
    )


@role_required("compliance", "rw")
def test_run_create(request, pk: int):
    implementation = get_object_or_404(
        ControlImplementation.objects.select_related("control", "system"), pk=pk
    )
    form = TestRunForm(request.POST or None, implementation=implementation)
    if request.method == "POST" and form.is_valid():
        run = form.save(commit=False)
        run.system = implementation.system
        run.created_by = request.user
        run.save()
        messages.success(request, f"Проверка зафиксирована: {run.get_result_display()}")
        return redirect("compliance:matrix")
    return render(
        request,
        "compliance/test_run_form.html",
        {"form": form, "implementation": implementation},
    )
