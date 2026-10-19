"""Сборка данных карты сети (SDD §5.10): обзор «площадки → роутеры → сегменты» и состав сегмента.

Чистые функции над моделями: ни сетевых вызовов, ни шаблонной логики — всё тестируется.
"""

from __future__ import annotations

import ipaddress

from django.db.models import Count, Q, QuerySet
from django.urls import reverse

from apps.discovery.models import RouterDevice
from apps.registry.models import Asset, Segment, Site

MISS_THRESHOLD = 3  # синхронно с discovery.services (импорт сервиса создал бы цикл приложений)

# Легенда карты: иконка (Bootstrap Icons) и цвет роли — те же, что у узлов графа.
ROLE_LEGEND: dict[str, tuple[str, str]] = {
    "server": ("bi-server", "#0b7285"),
    "workstation": ("bi-display", "#1c7ed6"),
    "printer": ("bi-printer", "#e8590c"),
    "network": ("bi-hdd-network", "#495057"),
    "medical": ("bi-heart-pulse", "#c92a2a"),
    "phone": ("bi-telephone", "#087f5b"),
    "camera": ("bi-camera-video", "#7048e8"),
    "other": ("bi-three-dots", "#868e96"),
    "unknown": ("bi-question-circle", "#adb5bd"),
}


def legend_roles(assets) -> list[dict]:
    """Элементы легенды: только типы, реально присутствующие в выборке (порядок — как в choices)."""
    present = {effective_role(asset) for asset in assets}
    return [
        {
            "code": value,
            "title": title,
            "icon": ROLE_LEGEND[value][0],
            "color": ROLE_LEGEND[value][1],
        }
        for value, title in Asset.DeviceRole.choices
        if value in present and value in ROLE_LEGEND
    ]


def effective_role(asset: Asset) -> str:
    """Роль для показа: ручная сильнее авто; если обе пусты — «unknown»."""
    if asset.device_role and asset.device_role != Asset.DeviceRole.UNKNOWN:
        return asset.device_role
    return asset.role_auto or Asset.DeviceRole.UNKNOWN


def asset_queryset() -> QuerySet[Asset]:
    """Активы с предвыбранными связями — для графа и таблицы состава."""
    return Asset.objects.select_related("segment", "site").prefetch_related(
        "system_components__system"
    )


def router_segment_links(
    segments: list[Segment] | None = None,
) -> list[tuple[RouterDevice, Segment, str]]:
    """Рёбра «роутер—сегмент»: интерфейсный адрес роутера лежит внутри CIDR сегмента."""
    if segments is None:
        segments = list(Segment.objects.all())
    networks = []
    for segment in segments:
        try:
            networks.append((segment, ipaddress.ip_network(segment.cidr, strict=False)))
        except ValueError:  # невалидный CIDR не должен ломать карту
            continue
    links: list[tuple[RouterDevice, Segment, str]] = []
    seen: set[tuple[int, int]] = set()
    for router in RouterDevice.objects.all():
        for item in router.addresses or []:
            try:
                ip = ipaddress.ip_interface(str(item.get("address", ""))).ip
            except ValueError:
                continue
            for segment, network in networks:
                key = (router.pk, segment.pk)
                if key in seen or ip not in network:
                    continue
                seen.add(key)
                links.append((router, segment, str(item.get("interface", ""))))
    return links


def router_router_links(
    routers: list[RouterDevice] | None = None,
) -> list[tuple[RouterDevice, RouterDevice, str]]:
    """Рёбра «роутер—роутер» по соседям (MNDP/LLDP/CDP): сосед опознаётся по адресу или имени.

    Источник — `/ip/neighbor` каждого роутера; связь рисуется, только если сосед — тоже
    наш роутер из инвентаря. Метка ребра — локальный интерфейс, через который виден сосед.
    """
    routers = list(routers if routers is not None else RouterDevice.objects.all())
    index: dict[str, RouterDevice] = {}
    for router in routers:
        index.setdefault(router.host.lower(), router)
        if router.name:
            index.setdefault(router.name.lower(), router)
        for item in router.addresses or []:
            index.setdefault(str(item.get("address", "")).split("/")[0].lower(), router)
    links: list[tuple[RouterDevice, RouterDevice, str]] = []
    seen: set[tuple[int, int]] = set()
    for router in routers:
        for neighbor in router.neighbors or []:
            candidates = (
                str(neighbor.get("address", "")).split("/")[0].lower(),
                str(neighbor.get("identity", "")).lower(),
            )
            other = next((index[key] for key in candidates if key and key in index), None)
            if other is None or other.pk == router.pk:
                continue
            pair = tuple(sorted((router.pk, other.pk)))
            if pair in seen:
                continue
            seen.add(pair)
            links.append((router, other, str(neighbor.get("interface", ""))))
    return links


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Русская форма слова для подписи площадки: 1 сегмент / 2 сегмента / 5 сегментов."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def overview_graph(site_id: int | None = None) -> dict:
    """Граф обзора: площадки (контейнеры), внутри — роутеры и сегменты, плюс связи.

    Роутер попадает в ту площадку, где у него больше всего сегментов: иначе общий ряд
    роутеров растягивал веер рёбер через всю схему и обзор терял читаемость (SDD §5.10).
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    segments = list(
        Segment.objects.select_related("site").annotate(
            asset_total=Count("assets", distinct=True),
            asset_active=Count(
                "assets", filter=Q(assets__miss_count__lt=MISS_THRESHOLD), distinct=True
            ),
            asset_unknown=Count(
                "assets",
                filter=Q(assets__owner_person__isnull=True, assets__system_components__isnull=True),
                distinct=True,
            ),
        )
    )
    visible_segments = [s for s in segments if site_id is None or s.site_id == site_id]

    site_stats: dict[int, dict[str, int]] = {}
    for segment in segments:
        if not segment.site_id:
            continue
        stats = site_stats.setdefault(segment.site_id, {"segments": 0, "assets": 0})
        stats["segments"] += 1
        stats["assets"] += segment.asset_total or 0

    sites = list(Site.objects.all())
    if site_id is not None:
        sites = [site for site in sites if site.pk == site_id]
    sites.sort(key=lambda site: (-site_stats.get(site.pk, {}).get("segments", 0), site.name))
    for site in sites:
        stats = site_stats.get(site.pk, {"segments": 0, "assets": 0})
        segments_count = stats["segments"]
        assets_count = stats["assets"]
        nodes.append(
            {
                "data": {
                    "id": f"site:{site.pk}",
                    "label": (
                        f"{site.name} · {segments_count} "
                        f"{_plural(segments_count, 'сегмент', 'сегмента', 'сегментов')} · "
                        f"{assets_count} {_plural(assets_count, 'актив', 'актива', 'активов')}"
                    ),
                    "type": "site",
                    "url": f"{reverse('registry:network_map')}?site={site.pk}",
                }
            }
        )

    for segment in visible_segments:
        data = {
            "id": f"segment:{segment.pk}",
            "label": f"{segment.name}\n{segment.cidr}",
            "type": "segment",
            "cidr": segment.cidr,
            "vlan": segment.vlan if segment.vlan is not None else "",
            "asset_total": segment.asset_total,
            "asset_active": segment.asset_active,
            "asset_unknown": segment.asset_unknown,
            "url": f"{reverse('registry:network_map')}?segment={segment.pk}",
        }
        if segment.site_id:
            data["parent"] = f"site:{segment.site_id}"
        nodes.append({"data": data})

    router_links = router_segment_links(visible_segments)
    votes: dict[int, dict[int, int]] = {}
    for router, segment, _interface in router_links:
        if segment.site_id:
            by_site = votes.setdefault(router.pk, {})
            by_site[segment.site_id] = by_site.get(segment.site_id, 0) + 1
    router_site = {
        router_pk: max(by_site.items(), key=lambda item: (item[1], -item[0]))[0]
        for router_pk, by_site in votes.items()
    }

    routers = list(RouterDevice.objects.all())
    if site_id is not None:
        routers = [router for router in routers if router_site.get(router.pk) == site_id]
    visible_routers = {router.pk for router in routers}
    for router in routers:
        data = {
            "id": f"router:{router.pk}",
            "label": router.name or router.host,
            "type": "router",
            "host": router.host,
        }
        if router.pk in router_site and router_site[router.pk] in {site.pk for site in sites}:
            data["parent"] = f"site:{router_site[router.pk]}"
        nodes.append({"data": data})

    for router, segment, interface in router_links:
        if router.pk not in visible_routers:
            continue
        edges.append(
            {
                "data": {
                    "id": f"link:{router.pk}:{segment.pk}",
                    "source": f"router:{router.pk}",
                    "target": f"segment:{segment.pk}",
                    "label": interface,
                    "type": "router-segment",
                }
            }
        )
    for left, right, interface in router_router_links(routers):
        edges.append(
            {
                "data": {
                    "id": f"rr:{left.pk}:{right.pk}",
                    "source": f"router:{left.pk}",
                    "target": f"router:{right.pk}",
                    "label": interface,
                    "type": "router-link",
                }
            }
        )
    return {"nodes": nodes, "edges": edges}


def segment_graph(segment: Segment, assets: list[Asset]) -> dict:
    """Граф сегмента: активы (в контейнере сегмента) и связи с ИС."""
    nodes: list[dict] = [
        {
            "data": {
                "id": "segment-root",
                "label": f"{segment.name}\n{segment.cidr}",
                "type": "segment-root",
                "cidr": segment.cidr,
                "vlan": segment.vlan if segment.vlan is not None else "",
            }
        }
    ]
    edges: list[dict] = []
    system_nodes: set[int] = set()

    for asset in assets:
        systems = [component.system for component in asset.system_components.all()]
        nodes.append(
            {
                "data": {
                    "id": f"asset:{asset.pk}",
                    "label": asset.hostname or asset.ip,
                    "parent": "segment-root",
                    "type": "asset",
                    "ip": asset.ip,
                    "mac": asset.mac,
                    "vendor": asset.mac_vendor,
                    "hostname": asset.hostname,
                    "role": effective_role(asset),
                    "role_auto": asset.role_auto,
                    "role_manual": ""
                    if asset.device_role == Asset.DeviceRole.UNKNOWN
                    else asset.device_role,
                    "os": asset.os_name or asset.os_family,
                    "ports": asset.ports or [],
                    "services": (asset.fingerprint or {}).get("services", []),
                    "status": "active" if asset.miss_count < MISS_THRESHOLD else "quiet",
                    "last_seen": asset.last_seen_at.strftime("%d.%m.%Y %H:%M"),
                    "systems": [system.name for system in systems],
                }
            }
        )
        for system in systems:
            system_id = f"system:{system.pk}"
            if system.pk not in system_nodes:
                system_nodes.add(system.pk)
                nodes.append(
                    {
                        "data": {
                            "id": system_id,
                            "label": system.name,
                            "type": "system",
                            "url": reverse("registry:system_detail", args=[system.pk]),
                        }
                    }
                )
            edges.append(
                {
                    "data": {
                        "id": f"member:{asset.pk}:{system.pk}",
                        "source": f"asset:{asset.pk}",
                        "target": system_id,
                        "type": "member",
                    }
                }
            )
    return {"nodes": nodes, "edges": edges}
