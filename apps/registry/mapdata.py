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


def overview_graph(site_id: int | None = None) -> dict:
    """Граф обзора: площадки (контейнеры), сегменты (внутри площадок), роутеры и связи."""
    nodes: list[dict] = []
    edges: list[dict] = []

    sites = Site.objects.all()
    if site_id is not None:
        sites = sites.filter(pk=site_id)
    for site in sites:
        nodes.append(
            {
                "data": {
                    "id": f"site:{site.pk}",
                    "label": site.name,
                    "type": "site",
                    "url": f"{reverse('registry:network_map')}?site={site.pk}",
                }
            }
        )

    segments = Segment.objects.select_related("site").annotate(
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
    if site_id is not None:
        segments = segments.filter(site_id=site_id)
    for segment in segments:
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

    for router in RouterDevice.objects.all():
        nodes.append(
            {
                "data": {
                    "id": f"router:{router.pk}",
                    "label": router.name or router.host,
                    "type": "router",
                    "host": router.host,
                }
            }
        )

    for router, segment, interface in router_segment_links(list(segments)):
        edges.append(
            {
                "data": {
                    "id": f"link:{router.pk}:{segment.pk}",
                    "source": f"router:{router.pk}",
                    "target": f"segment:{segment.pk}",
                    "label": interface,
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
