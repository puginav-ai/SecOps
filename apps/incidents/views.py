"""UI инцидентов: реестр, таймеры стадий, отправка с evidence, закрытие (неделя 10)."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.access import module_access, role_required
from apps.incidents import services
from apps.incidents.forms import IncidentForm, StageSendForm
from apps.incidents.models import Incident, IncidentNotification


@role_required("incidents")
def incident_list(request):
    active = Incident.objects.exclude(status=Incident.Status.CLOSED).select_related("system")
    closed = Incident.objects.filter(status=Incident.Status.CLOSED).order_by("-closed_at")[:20]
    return render(
        request,
        "incidents/list.html",
        {
            "active": active,
            "closed": closed,
            "overdue_count": services.overdue_stages().count(),
            "can_edit": module_access(request.user, "incidents") == "rw",
        },
    )


@role_required("incidents", "rw")
def incident_create(request):
    form = IncidentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        incident = services.create_incident(
            kind=form.cleaned_data["kind"],
            detected_at=form.cleaned_data["detected_at"],
            system=form.cleaned_data["system"],
            severity=form.cleaned_data["severity"],
            description=form.cleaned_data["description"],
            user=request.user,
        )
        messages.success(
            request, f"Инцидент #{incident.pk} зарегистрирован; стадий: {incident.stages.count()}"
        )
        return redirect("incidents:detail", pk=incident.pk)
    return render(request, "incidents/form.html", {"form": form})


@role_required("incidents")
def incident_detail(request, pk: int):
    incident = get_object_or_404(Incident.objects.select_related("system"), pk=pk)
    stages = list(incident.stages.select_related("rule", "evidence").order_by("deadline_at"))
    for stage in stages:
        stage.form = StageSendForm(user=request.user) if stage.sent_at is None else None
    return render(
        request,
        "incidents/detail.html",
        {
            "incident": incident,
            "stages": stages,
            "can_edit": module_access(request.user, "incidents") == "rw",
        },
    )


@role_required("incidents", "rw")
@require_POST
def stage_send(request, pk: int, stage_id: int):
    incident = get_object_or_404(Incident, pk=pk)
    stage = get_object_or_404(IncidentNotification, pk=stage_id, incident=incident)
    form = StageSendForm(request.POST, user=request.user)
    if form.is_valid():
        try:
            services.mark_stage_sent(
                stage,
                evidence=form.cleaned_data["evidence"],
                channel=form.cleaned_data["channel"],
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, f"Стадия «{stage.stage_code}» закрыта")
    else:
        messages.error(request, f"Не удалось закрыть стадию: {form.errors.as_text()}")
    return redirect("incidents:detail", pk=incident.pk)


@role_required("incidents", "rw")
@require_POST
def incident_status(request, pk: int):
    incident = get_object_or_404(Incident, pk=pk)
    target = request.POST.get("status", "")
    if target == Incident.Status.INVESTIGATING:
        services.start_investigation(incident)
        messages.success(request, "Инцидент переведён в разбор")
    return redirect("incidents:detail", pk=incident.pk)


@role_required("incidents", "rw")
@require_POST
def incident_close(request, pk: int):
    incident = get_object_or_404(Incident, pk=pk)
    try:
        services.close_incident(incident)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, f"Инцидент #{incident.pk} закрыт")
    return redirect("incidents:detail", pk=incident.pk)
