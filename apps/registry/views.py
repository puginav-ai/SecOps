"""UI реестра: сегменты (network scopes) и обзор активов (SDD §5.1–5.2)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.access import module_access, role_required
from apps.discovery.services import MISS_THRESHOLD
from apps.registry.forms import SegmentForm
from apps.registry.models import Asset, Segment

NEW_ASSETS_HOURS = 24


@role_required("registry")
def segment_list(request):
    segments = Segment.objects.select_related("site", "owner_person").order_by("site__name", "name")
    return render(
        request,
        "registry/segments.html",
        {"segments": segments, "can_edit": module_access(request.user, "registry") == "rw"},
    )


@role_required("registry", "rw")
def segment_create(request):
    form = SegmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        segment = form.save()
        messages.success(request, f"Сегмент «{segment.name}» сохранён")
        return redirect("registry:segment_list")
    return render(request, "registry/segment_form.html", {"form": form, "title": "Новый сегмент"})


@role_required("registry", "rw")
def segment_edit(request, pk: int):
    segment = get_object_or_404(Segment, pk=pk)
    form = SegmentForm(request.POST or None, instance=segment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Сегмент «{segment.name}» сохранён")
        return redirect("registry:segment_list")
    return render(
        request,
        "registry/segment_form.html",
        {"form": form, "title": f"Сегмент «{segment.name}»"},
    )


@role_required("registry", "rw")
@require_POST
def segment_delete(request, pk: int):
    segment = get_object_or_404(Segment, pk=pk)
    try:
        segment.delete()
    except ProtectedError:
        messages.error(
            request,
            "Нельзя удалить сегмент: есть активы или история сканов. "
            "Отключите скан вместо удаления.",
        )
    else:
        messages.success(request, "Сегмент удалён")
    return redirect("registry:segment_list")


@role_required("registry")
def asset_list(request):
    """Обзор активов: распределение по площадкам/сегментам и новые за сутки (SDD §5.2)."""
    assets = Asset.objects.select_related("site", "segment").order_by("ip")
    segment = None
    if segment_id := request.GET.get("segment"):
        segment = get_object_or_404(Segment, pk=segment_id)
        assets = assets.filter(segment=segment)

    cutoff = timezone.now() - timedelta(hours=NEW_ASSETS_HOURS)
    new_ids = set(assets.filter(last_seen_at__gte=cutoff).values_list("pk", flat=True))
    context = {
        "assets": assets,
        "segments": Segment.objects.order_by("name"),
        "segment": segment,
        "new_ids": new_ids,
        "new_count": len(new_ids),
        "active_total": assets.filter(miss_count__lt=MISS_THRESHOLD).count(),
        "total": assets.count(),
        "miss_threshold": MISS_THRESHOLD,
        "by_site": assets.values("site__name").annotate(total=Count("id")).order_by("site__name"),
        "by_segment": assets.values("segment__name")
        .annotate(total=Count("id"))
        .order_by("segment__name"),
    }
    return render(request, "registry/assets.html", context)
