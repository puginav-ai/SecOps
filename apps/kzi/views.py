"""UI КЗИ: список оценок, создание, ввод значений, закрытие и «почему не 1» (недели 7–8)."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.access import module_access, role_required
from apps.core.export import csv_response
from apps.evidence.models import EvidenceObject
from apps.kzi import services
from apps.kzi.forms import AssessmentForm
from apps.kzi.models import (
    Assessment,
    KpiGroup,
    KpiItem,
    KpiValue,
    RemediationPlan,
    RemediationTask,
)


@role_required("kzi")
def assessment_list(request):
    assessments = Assessment.objects.select_related().prefetch_related("scope__system")
    return render(
        request,
        "kzi/list.html",
        {
            "assessments": assessments,
            "can_edit": module_access(request.user, "kzi") == "rw",
        },
    )


@role_required("kzi", "rw")
def assessment_create(request):
    form = AssessmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        assessment = form.save()
        messages.success(request, "Оценка создана — заполните значения KPI")
        return redirect("kzi:detail", pk=assessment.pk)
    return render(request, "kzi/form.html", {"form": form})


@role_required("kzi")
def assessment_detail(request, pk: int):
    assessment = get_object_or_404(Assessment.objects.prefetch_related("scope__system"), pk=pk)
    groups = KpiGroup.objects.prefetch_related("items").order_by("sort")
    systems = [link.system for link in assessment.scope.select_related("system")]
    stored = {
        (value.system_id, value.kpi_item_id): value
        for value in assessment.values.select_related("evidence")
    }
    grid = [
        {
            "group": group,
            "items": [
                {
                    "item": item,
                    "cells": [
                        {"system": system, "stored": stored.get((system.pk, item.pk))}
                        for system in systems
                    ],
                }
                for item in group.items.order_by("sort", "code")
            ],
        }
        for group in groups
    ]
    preview = services.compute_snapshot(assessment) if systems else None
    plans = assessment.remediation_plans.prefetch_related(
        "tasks__system", "tasks__kpi_item", "tasks__owner_person"
    )
    return render(
        request,
        "kzi/detail.html",
        {
            "assessment": assessment,
            "grid": grid,
            "systems": systems,
            "evidences": EvidenceObject.objects.order_by("-created_at")[:200],
            "preview": preview,
            "plans": plans,
            "can_edit": module_access(request.user, "kzi") == "rw",
        },
    )


@role_required("kzi", "rw")
@require_POST
def assessment_save_values(request, pk: int):
    assessment = get_object_or_404(Assessment, pk=pk)
    if assessment.status == Assessment.Status.CLOSED:
        messages.error(request, "Оценка закрыта — значения заблокированы")
        return redirect("kzi:detail", pk=assessment.pk)

    systems = [link.system for link in assessment.scope.select_related("system")]
    items = list(KpiItem.objects.all())
    saved, errors = 0, []
    for system in systems:
        for item in items:
            raw = request.POST.get(f"value-{system.pk}-{item.pk}", "")
            evidence_raw = request.POST.get(f"evidence-{system.pk}-{item.pk}", "").strip()
            try:
                value = services.parse_value(raw)
            except ValidationError as exc:
                errors.append(f"{system.name}/{item.code}: {exc.messages[0]}")
                continue
            record, _created = KpiValue.objects.get_or_create(
                assessment=assessment, system=system, kpi_item=item
            )
            record.value = value
            record.evidence_id = int(evidence_raw) if evidence_raw else None
            record.save(update_fields=["value", "evidence"])
            saved += 1
    if errors:
        messages.error(request, "Ошибки: " + "; ".join(errors[:5]))
    else:
        messages.success(request, f"Сохранено значений: {saved}")
    return redirect("kzi:detail", pk=assessment.pk)


@role_required("kzi", "rw")
@require_POST
def assessment_close(request, pk: int):
    assessment = get_object_or_404(Assessment, pk=pk)
    if assessment.status == Assessment.Status.CLOSED:
        messages.error(request, "Оценка уже закрыта")
        return redirect("kzi:detail", pk=assessment.pk)
    try:
        snapshot = services.close_assessment(assessment)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(
            request,
            f"Оценка закрыта: КЗИ {snapshot['final']} — {snapshot['verdict']} "
            f"(донор: {snapshot['donor'] or '—'})",
        )
    return redirect("kzi:detail", pk=assessment.pk)


@role_required("kzi", "rw")
@require_POST
def remediation_create(request, pk: int):
    assessment = get_object_or_404(Assessment, pk=pk)
    try:
        plan = services.create_remediation_plan(assessment)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, f"План создан: задач {plan.tasks.count()}")
    return redirect("kzi:detail", pk=assessment.pk)


@role_required("kzi", "rw")
@require_POST
def task_set_status(request, plan_id: int, task_id: int):
    task = get_object_or_404(RemediationTask, pk=task_id, plan_id=plan_id)
    new_status = request.POST.get("status")
    if new_status in {RemediationTask.Status.DONE, RemediationTask.Status.CANCELLED}:
        task.status = new_status
        task.save(update_fields=["status"])
        messages.success(request, f"Задача обновлена: {task.get_status_display()}")
    return redirect("kzi:detail", pk=task.plan.assessment_id)


@role_required("kzi")
def plan_export_csv(request, pk: int):
    """Выгрузка плана мероприятий (CSV, защита от инъекций — общий экспорт)."""
    plan = get_object_or_404(RemediationPlan.objects.select_related("assessment"), pk=pk)
    rows = [
        [
            task.system.name if task.system else "—",
            task.kpi_item.code if task.kpi_item else "—",
            task.title,
            str(task.owner_person) if task.owner_person else "—",
            task.due_at.strftime("%d.%m.%Y") if task.due_at else "—",
            task.get_status_display(),
        ]
        for task in plan.tasks.select_related("system", "kpi_item", "owner_person")
    ]
    header = ["ИС", "KPI", "Задача", "Ответственный", "Срок", "Статус"]
    return csv_response(f"plan-{plan.pk}.csv", header, rows)
