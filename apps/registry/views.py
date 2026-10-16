"""UI реестра: сегменты (network scopes) и обзор активов (SDD §5.1–5.2)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.access import FULL_REGISTRY_ROLES, module_access, role_required, user_roles
from apps.discovery.services import MISS_THRESHOLD
from apps.registry.forms import PersonForm, SegmentForm, SystemComponentForm, SystemForm
from apps.registry.models import Asset, Person, Segment, System, SystemComponent

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


@role_required("registry")
def unknown_assets(request):
    """Unknown assets: активы без привязки к ИС и без ответственного (SDD §5.1)."""
    assets = (
        Asset.objects.filter(owner_person__isnull=True, system_components__isnull=True)
        .select_related("segment")
        .order_by("-first_seen_at")
    )
    return render(
        request,
        "registry/unknown_assets.html",
        {"assets": assets, "total": assets.count(), "miss_threshold": MISS_THRESHOLD},
    )


def _visible_systems(request):
    """ИС с учётом роли: «system_owner» видит только свои (SDD §4)."""
    systems = System.objects.select_related("site", "owner_person").order_by("name")
    roles = user_roles(request.user)
    if "system_owner" in roles and not roles & FULL_REGISTRY_ROLES:
        systems = systems.filter(owner_person__user=request.user)
    return systems


@role_required("registry")
def system_list(request):
    return render(
        request,
        "registry/systems.html",
        {
            "systems": _visible_systems(request),
            "can_edit": module_access(request.user, "registry") == "rw",
        },
    )


@role_required("registry", "rw")
def system_create(request):
    form = SystemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        system = form.save()
        messages.success(request, f"ИС «{system.name}» сохранена")
        return redirect("registry:system_list")
    return render(request, "registry/system_form.html", {"form": form, "title": "Новая ИС"})


@role_required("registry", "rw")
def system_edit(request, pk: int):
    system = get_object_or_404(_visible_systems(request), pk=pk)
    form = SystemForm(request.POST or None, instance=system)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"ИС «{system.name}» сохранена")
        return redirect("registry:system_list")
    return render(
        request, "registry/system_form.html", {"form": form, "title": f"ИС «{system.name}»"}
    )


@role_required("registry")
def system_detail(request, pk: int):
    system = get_object_or_404(_visible_systems(request), pk=pk)
    components = system.components.select_related("asset").order_by("asset__ip")
    return render(
        request,
        "registry/system_detail.html",
        {
            "system": system,
            "components": components,
            "form": SystemComponentForm(system=system),
            "can_edit": module_access(request.user, "registry") == "rw",
        },
    )


@role_required("registry", "rw")
@require_POST
def component_add(request, pk: int):
    system = get_object_or_404(System, pk=pk)
    form = SystemComponentForm(request.POST, system=system)
    if form.is_valid():
        component = form.save(commit=False)
        component.system = system
        component.save()
        messages.success(request, f"Актив {component.asset.ip} привязан к «{system.name}»")
    else:
        messages.error(request, f"Не удалось привязать: {form.errors.as_text()}")
    return redirect("registry:system_detail", pk=system.pk)


@role_required("registry", "rw")
@require_POST
def component_remove(request, pk: int, component_id: int):
    system = get_object_or_404(System, pk=pk)
    SystemComponent.objects.filter(pk=component_id, system=system).delete()
    messages.success(request, "Привязка удалена")
    return redirect("registry:system_detail", pk=system.pk)


@role_required("registry")
def person_list(request):
    people = Person.objects.select_related("user").order_by("fio")
    return render(
        request,
        "registry/persons.html",
        {"people": people, "can_edit": module_access(request.user, "registry") == "rw"},
    )


@role_required("registry", "rw")
def person_create(request):
    form = PersonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        person = form.save()
        messages.success(request, f"«{person.fio}» сохранён")
        return redirect("registry:person_list")
    return render(request, "registry/person_form.html", {"form": form, "title": "Новый человек"})


@role_required("registry", "rw")
def person_edit(request, pk: int):
    person = get_object_or_404(Person, pk=pk)
    form = PersonForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"«{person.fio}» сохранён")
        return redirect("registry:person_list")
    return render(request, "registry/person_form.html", {"form": form, "title": f"«{person.fio}»"})
