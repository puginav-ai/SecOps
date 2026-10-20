"""UI реестра: сегменты (network scopes), карта сети и обзор активов (SDD §5.1–5.2, §5.10)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.access import FULL_REGISTRY_ROLES, module_access, role_required, user_roles
from apps.core.export import xlsx_response
from apps.discovery.models import RouterDevice, ScanRun
from apps.discovery.services import MISS_THRESHOLD
from apps.discovery.tasks import scan_segment
from apps.registry import mapdata
from apps.registry.forms import PersonForm, SegmentForm, SystemComponentForm, SystemForm
from apps.registry.models import Asset, Person, Segment, Site, System, SystemComponent

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


# --- карта сети (SDD §5.10) ------------------------------------------------------------

ASSET_SORTS = {
    "ip": ("ip",),
    "-ip": ("-ip",),
    "hostname": ("hostname", "ip"),
    "role": ("role_auto", "ip"),
    "last_seen": ("last_seen_at", "ip"),
    "-last_seen": ("-last_seen_at", "ip"),
}
GRAPH_NODE_LIMIT = 400
TABLE_ROW_LIMIT = 500
XLSX_ROW_LIMIT = 5000


def _base_query(request) -> str:
    """Query-строка без sort — для ссылок сортировки в таблице."""
    params = request.GET.copy()
    params.pop("sort", None)
    return params.urlencode()


def _overview_size_urls(request, current: str) -> dict[str, str]:
    """Ссылки переключателя «размер плиток сегментов» с сохранением site/find."""
    urls = {}
    for mode in ("count", "same"):
        params = request.GET.copy()
        if mode == "count":
            params.pop("size", None)  # значение по умолчанию — без параметра
        else:
            params["size"] = mode
        urls[mode] = "?" + params.urlencode() if params else "?"
    return urls


def _overview_reset_url(request) -> str:
    """Ссылка «сбросить поиск»: убирает find, сохраняет site/size."""
    params = request.GET.copy()
    params.pop("find", None)
    return "?" + params.urlencode() if params else "?"


def _map_assets(segment: Segment, params):
    """Активы сегмента с фильтрами карты: роль, вендор, порт, продукт, ИС, статус, поиск."""
    assets = mapdata.asset_queryset().filter(segment=segment)

    role = (params.get("role") or "").strip()
    if role:
        # ручная роль главнее: фильтр учитывает и её, и авто-классификацию
        assets = assets.filter(
            Q(device_role=role) | Q(device_role=Asset.DeviceRole.UNKNOWN, role_auto=role)
        )
    vendor = (params.get("vendor") or "").strip()
    if vendor:
        assets = assets.filter(mac_vendor__icontains=vendor)
    port = (params.get("port") or "").strip()
    if port.isdigit():
        assets = assets.filter(ports__contains=[int(port)])
    product = (params.get("product") or "").strip()
    if product:
        assets = assets.filter(software__icontains=product)
    system = (params.get("system") or "").strip()
    if system == "with":
        assets = assets.filter(system_components__isnull=False).distinct()
    elif system == "without":
        assets = assets.filter(system_components__isnull=True)
    status = (params.get("status") or "").strip()
    if status == "active":
        assets = assets.filter(miss_count__lt=MISS_THRESHOLD)
    elif status == "quiet":
        assets = assets.filter(miss_count__gte=MISS_THRESHOLD)
    query = (params.get("q") or "").strip()
    if query:
        assets = assets.filter(
            Q(ip__icontains=query) | Q(hostname__icontains=query) | Q(mac__icontains=query)
        )
    return assets


@role_required("registry")
def network_map(request):
    """Карта сети: обзор «площадки → роутеры → сегменты» или состав выбранного сегмента."""
    segments = Segment.objects.select_related("site").order_by("site__name", "name")
    segment = None
    segment_id = (request.GET.get("segment") or "").strip()
    if segment_id.isdigit():
        segment = get_object_or_404(segments, pk=int(segment_id))
    site_param = (request.GET.get("site") or "").strip()
    site_id = int(site_param) if site_param.isdigit() else None

    context: dict = {
        "sites": Site.objects.all(),
        "segments": segments.filter(site_id=site_id) if site_id else segments,
        "site_id": site_id,
        "segment": segment,
        "can_edit": module_access(request.user, "registry") == "rw",
        "roles": Asset.DeviceRole.choices,
        "miss_threshold": MISS_THRESHOLD,
        "filters": {
            key: (request.GET.get(key) or "").strip()
            for key in ("role", "vendor", "port", "product", "system", "status", "q", "sort")
        },
    }

    if segment is None:
        find_query = (request.GET.get("find") or "").strip()
        size_mode = "same" if request.GET.get("size") == "same" else "count"
        found = mapdata.search_map(find_query) if find_query else None
        graph = mapdata.overview_graph(
            site_id,
            sized=size_mode == "count",
            found_segment_ids=tuple(found["segment_ids"]) if found else (),
        )
        context["graph"] = graph
        context["graph_types"] = {node["data"]["type"] for node in graph["nodes"]}
        context["graph_edge_types"] = {edge["data"].get("type", "plain") for edge in graph["edges"]}
        context["routers_total"] = RouterDevice.objects.count()
        context["graph_has_core"] = any(node["data"].get("core") for node in graph["nodes"])
        context["find_query"] = find_query
        context["found"] = found
        context["found_segment_ids"] = found["segment_ids"] if found else []
        context["size_mode"] = size_mode
        context["size_urls"] = _overview_size_urls(request, size_mode)
        context["reset_find_url"] = _overview_reset_url(request)
        return render(request, "registry/map.html", context)

    assets = _map_assets(segment, request.GET)
    sort = context["filters"]["sort"] if context["filters"]["sort"] in ASSET_SORTS else "ip"
    ordered = assets.order_by(*ASSET_SORTS[sort])
    graph_assets = list(ordered[:GRAPH_NODE_LIMIT])
    graph = mapdata.segment_graph(segment, graph_assets)
    legend_roles = mapdata.legend_roles(graph_assets)
    legend_os = mapdata.legend_os(graph_assets)
    if legend_os:
        # Иконки роли различаются по ОС — общий пункт роли убираем, только если
        # варианты ОС действительно есть (иначе оставляем АРМ/сервер как раньше)
        roles_with_os = {item["role"] for item in legend_os}
        legend_roles = [item for item in legend_roles if item["code"] not in roles_with_os]
    context.update(
        {
            "graph": graph,
            "graph_types": {node["data"]["type"] for node in graph["nodes"]},
            "graph_edge_types": {edge["data"].get("type", "plain") for edge in graph["edges"]},
            "legend_roles": legend_roles,
            "legend_os": legend_os,
            "legend_quiet": any(asset.miss_count >= MISS_THRESHOLD for asset in graph_assets),
            "graph_total": assets.count(),
            "graph_shown": len(graph_assets),
            "assets": list(ordered[:TABLE_ROW_LIMIT]),
            "assets_total": assets.count(),
            "active_total": assets.filter(miss_count__lt=MISS_THRESHOLD).count(),
            "quiet_total": assets.filter(miss_count__gte=MISS_THRESHOLD).count(),
            "unknown_total": assets.filter(system_components__isnull=True).count(),
            "systems": System.objects.filter(components__asset__segment=segment)
            .distinct()
            .order_by("name"),
            "vendors": Asset.objects.filter(segment=segment)
            .exclude(mac_vendor="")
            .values_list("mac_vendor", flat=True)
            .distinct()
            .order_by("mac_vendor")[:80],
            "base_query": _base_query(request),
        }
    )
    return render(request, "registry/map.html", context)


@role_required("registry", "rw")
@require_POST
def segment_scan_now(request, pk: int):
    """«Просканировать сейчас»: ручной запуск скана сегмента (окно скана не проверяется)."""
    segment = get_object_or_404(Segment, pk=pk)
    target = f"{reverse('registry:network_map')}?segment={segment.pk}"
    if not segment.scan_enabled:
        messages.error(
            request, f"Скан сегмента «{segment.name}» выключен — включите его в карточке"
        )
        return redirect(target)
    scan_segment.apply_async(args=[segment.pk, ScanRun.Trigger.MANUAL.value], queue="scan")
    messages.success(request, f"Скан сегмента «{segment.name}» поставлен в очередь")
    return redirect(target)


@role_required("registry")
def segment_assets_xlsx(request):
    """Выгрузка состава сегмента с текущими фильтрами карты (SDD §5.10)."""
    segment_id = (request.GET.get("segment") or "").strip()
    if not segment_id.isdigit():
        raise Http404("выгрузка доступна для конкретного сегмента")
    segment = get_object_or_404(Segment, pk=int(segment_id))

    assets = _map_assets(segment, request.GET).order_by("ip")[:XLSX_ROW_LIMIT]
    role_titles = dict(Asset.DeviceRole.choices)
    rows = []
    for asset in assets:
        rows.append(
            [
                asset.ip,
                asset.mac or "—",
                asset.mac_vendor or "—",
                asset.hostname or "—",
                role_titles.get(asset.device_role, ""),
                role_titles.get(asset.role_auto, "")
                if asset.device_role == Asset.DeviceRole.UNKNOWN
                else "",
                asset.os_name or asset.os_family or "—",
                ", ".join(str(port) for port in (asset.ports or [])),
                asset.software or "—",
                "; ".join(component.system.name for component in asset.system_components.all())
                or "—",
                str(asset.owner_person) if asset.owner_person else "—",
                timezone.localtime(asset.last_seen_at).strftime("%d.%m.%Y %H:%M"),
                "в сети" if asset.miss_count < MISS_THRESHOLD else "молчит",
            ]
        )
    return xlsx_response(
        f"segment-{segment.pk}-assets.xlsx",
        [
            "IP",
            "MAC",
            "Вендор",
            "Имя",
            "Роль (ручная)",
            "Роль (авто)",
            "ОС",
            "Порты",
            "Службы/ПО",
            "ИС",
            "Ответственный",
            "Последний отклик",
            "Статус",
        ],
        rows,
    )
