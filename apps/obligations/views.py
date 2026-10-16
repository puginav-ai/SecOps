"""UI обязательств: список/календарь сроков, закрытие, отмена (SDD §5.5)."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.access import role_required
from apps.obligations.forms import ObligationCloseForm
from apps.obligations.models import ObligationInstance, ObligationTemplate


@role_required("obligations")
def obligation_list(request):
    active = (
        ObligationInstance.objects.filter(
            status__in=[
                ObligationInstance.Status.PLANNED,
                ObligationInstance.Status.DUE_SOON,
                ObligationInstance.Status.OVERDUE,
            ]
        )
        .select_related("template", "owner_person")
        .order_by("due_at")
    )
    overdue = [item for item in active if item.status == ObligationInstance.Status.OVERDUE]
    soon = [item for item in active if item.status == ObligationInstance.Status.DUE_SOON]
    planned = [item for item in active if item.status == ObligationInstance.Status.PLANNED]
    recent_closed = (
        ObligationInstance.objects.filter(
            status__in=[ObligationInstance.Status.DONE, ObligationInstance.Status.CANCELLED]
        )
        .select_related("template", "owner_person")
        .order_by("-closed_at")[:20]
    )
    return render(
        request,
        "obligations/list.html",
        {
            "overdue": overdue,
            "soon": soon,
            "planned": planned,
            "recent_closed": recent_closed,
            "templates_count": ObligationTemplate.objects.count(),
        },
    )


@role_required("obligations", "rw")
def obligation_close(request, pk: int):
    instance = get_object_or_404(ObligationInstance.objects.select_related("template"), pk=pk)
    form = ObligationCloseForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        instance.status = ObligationInstance.Status.DONE
        instance.closed_at = timezone.now()
        instance.closure_evidence = form.cleaned_data["evidence"]
        instance.save(update_fields=["status", "closed_at", "closure_evidence"])
        messages.success(request, f"«{instance.template.name}» закрыто")
        return redirect("obligations:list")
    return render(request, "obligations/close.html", {"form": form, "instance": instance})


@role_required("obligations", "rw")
@require_POST
def obligation_cancel(request, pk: int):
    instance = get_object_or_404(ObligationInstance, pk=pk)
    instance.status = ObligationInstance.Status.CANCELLED
    instance.closed_at = timezone.now()
    instance.save(update_fields=["status", "closed_at"])
    messages.success(request, f"«{instance.template.name}» отменено")
    return redirect("obligations:list")
