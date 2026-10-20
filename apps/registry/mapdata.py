"""Сборка данных карты сети (SDD §5.10): обзор «площадки → роутеры → сегменты» и состав сегмента.

Чистые функции над моделями: ни сетевых вызовов, ни шаблонной логики — всё тестируется.
"""

from __future__ import annotations

import ipaddress
import re

from django.db.models import Count, Q, QuerySet
from django.urls import reverse

from apps.discovery.models import RouterDevice
from apps.registry.models import Asset, Segment, Site

MISS_THRESHOLD = 3  # синхронно с discovery.services (импорт сервиса создал бы цикл приложений)

# Плитки сегментов на обзоре: (порог «от», ширина, высота, шрифт, без CIDR).
# Пустые и служебные сегменты — мелкие серые чипы, наполненные — крупнее (SDD §5.10).
SEGMENT_TILE_BUCKETS: tuple[tuple[int, int, int, int, bool], ...] = (
    (0, 132, 40, 10, True),
    (1, 168, 42, 11, False),
    (10, 208, 48, 12, False),
    (50, 248, 56, 12, False),
)
UNIFORM_TILE = (200, 48, 12)


def segment_tile(asset_total: int, sized: bool) -> tuple[int, int, int, bool]:
    """Размер плитки сегмента: (ширина, высота, шрифт, компактная подпись без CIDR)."""
    if not sized:
        return (*UNIFORM_TILE, False)
    for threshold, width, height, font_size, compact in reversed(SEGMENT_TILE_BUCKETS):
        if asset_total >= threshold:
            return width, height, font_size, compact
    return 132, 40, 10, True


# Легенда карты: иконка (Bootstrap Icons) и цвет роли — те же, что у узлов графа.
ROLE_LEGEND: dict[str, tuple[str, str]] = {
    "server": ("bi-server", "#0b7285"),
    "workstation": ("bi-display", "#1c7ed6"),
    "printer": ("bi-printer", "#e8590c"),
    "network": ("bi-hdd-network", "#495057"),
    "medical": ("bi-heart-pulse", "#c92a2a"),
    "phone": ("bi-telephone", "#087f5b"),
    "camera": ("bi-camera-video", "#7048e8"),
    "mobile": ("bi-phone", "#c2255c"),
    "ap": ("bi-wifi", "#0c8599"),
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


def os_variant(asset: Asset) -> str:
    """ОС-вариант для иконки АРМ/сервера: windows|astra|redos|ubuntu|linux|""."""
    text = f"{asset.os_name or ''} {asset.os_family or ''}".lower()
    if "windows" in text:
        return "windows"
    if "astra" in text:
        return "astra"
    if "red os" in text or "redos" in text:
        return "redos"
    if "ubuntu" in text:
        return "ubuntu"
    if any(marker in text for marker in ("linux", "debian", "centos", "almalinux", "rocky")):
        return "linux"
    return ""


# Фирменные иконки ОС (звезда Astra, три квадрата РЕДОС) вместо глифа Bootstrap Icons
OS_ICON_IMAGE: dict[tuple[str, str], str] = {
    ("workstation", "astra"): "vendor/icons/os/astra.svg",
    ("workstation", "redos"): "vendor/icons/os/redos.svg",
}

# Подписи и иконки ОС-вариантов (Bootstrap Icons, те же глифы, что в вендорных SVG)
OS_ICON_LEGEND: dict[tuple[str, str], tuple[str, str]] = {
    ("server", "windows"): ("bi-server", "сервер · Windows"),
    ("server", "linux"): ("bi-hdd-rack", "сервер · Linux"),
    ("server", "astra"): ("bi-hdd-rack", "сервер · Astra Linux"),
    ("server", "redos"): ("bi-hdd-rack", "сервер · RED OS"),
    ("server", "ubuntu"): ("bi-hdd-rack", "сервер · Ubuntu"),
    ("workstation", "windows"): ("bi-windows", "АРМ · Windows"),
    ("workstation", "astra"): ("bi-pc-display", "АРМ · Astra Linux"),
    ("workstation", "redos"): ("bi-pc", "АРМ · RED OS"),
    ("workstation", "ubuntu"): ("bi-ubuntu", "АРМ · Ubuntu"),
    ("workstation", "linux"): ("bi-display", "АРМ · другая Linux"),
}


def legend_os(assets) -> list[dict]:
    """Элементы легенды по ОС-вариантам АРМ/серверов, реально присутствующим в выборке.

    Активы без данных об ОС остаются под общим пунктом роли (АРМ/сервер) — их не
    помечаем «ОС не определена», чтобы не раздувать легенду.
    """
    role_order = {"server": 0, "workstation": 1}
    present = {
        (effective_role(asset), os_variant(asset))
        for asset in assets
        if effective_role(asset) in role_order and os_variant(asset)
    }
    return [
        {
            "role": role,
            "icon": OS_ICON_LEGEND[(role, variant)][0],
            "title": OS_ICON_LEGEND[(role, variant)][1],
            "color": ROLE_LEGEND[role][1],
            "image": OS_ICON_IMAGE.get((role, variant), ""),
        }
        for role, variant in sorted(
            present, key=lambda item: (role_order[item[0]], OS_ICON_LEGEND[item][1])
        )
    ]


def asset_queryset() -> QuerySet[Asset]:
    """Активы с предвыбранными связями — для графа и таблицы состава."""
    return Asset.objects.select_related("segment", "site").prefetch_related(
        "system_components__system"
    )


def router_segment_links(
    segments: list[Segment] | None = None,
) -> list[tuple[RouterDevice, Segment, str, str]]:
    """Рёбра «роутер—сегмент»: интерфейсный адрес роутера лежит внутри CIDR сегмента.

    Возвращает и IP интерфейса: по нему выбирается основной шлюз сегмента (минимальный),
    остальные связи на обзорной схеме не рисуем — меньше длинных пересекающихся линий.
    """
    if segments is None:
        segments = list(Segment.objects.all())
    networks = []
    for segment in segments:
        try:
            networks.append((segment, ipaddress.ip_network(segment.cidr, strict=False)))
        except ValueError:  # невалидный CIDR не должен ломать карту
            continue
    links: list[tuple[RouterDevice, Segment, str, str]] = []
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
                links.append((router, segment, str(item.get("interface", "")), str(ip)))
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


def _same_subnet24(left: str, right: str) -> bool:
    """Одинаковая /24 — для пары «Континентов» в одном служебном /29."""
    try:
        return ipaddress.ip_network(f"{left}/24", strict=False) == ipaddress.ip_network(
            f"{right}/24", strict=False
        )
    except ValueError:
        return False


def overview_graph(
    site_id: int | None = None,
    *,
    sized: bool = True,
    found_segment_ids: tuple[int, ...] = (),
    url_query: str = "",
) -> dict:
    """Граф обзора: площадки (контейнеры), внутри — роутеры и сегменты, плюс связи.

    sized — размер плитки сегмента пропорционально числу активов (пустые — мелкие чипы);
    found_segment_ids — сегменты, попавшие в поиск: подсвечиваются и получают флаг `found`.
    Роутер попадает в ту площадку, где у него больше всего сегментов: иначе общий ряд
    роутеров растягивал веер рёбер через всю схему и обзор терял читаемость (SDD §5.10).
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    segment_suffix = f"&{url_query}" if url_query else ""

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

    router_links = router_segment_links(visible_segments)
    # Основной шлюз сегмента — роутер с минимальным интерфейсным IP (обычно .1).
    # Рисуем только его связь: остальные — дублирующие и превращают схему в паутину.
    primary_links: dict[int, tuple[RouterDevice, Segment, str, str]] = {}
    for link in router_links:
        current = primary_links.get(link[1].pk)
        if current is None or ipaddress.ip_address(link[3]) < ipaddress.ip_address(current[3]):
            primary_links[link[1].pk] = link

    for segment in visible_segments:
        total = segment.asset_total or 0
        tile_w, tile_h, font_size, compact = segment_tile(total, sized)
        plural_assets = _plural(total, "актив", "актива", "активов")
        data = {
            "id": f"segment:{segment.pk}",
            "label": f"{segment.name}\n{segment.cidr}" if not compact else segment.name,
            "summary": f"{segment.name} · {segment.cidr} · {total} {plural_assets}",
            "type": "segment",
            "cidr": segment.cidr,
            "vlan": segment.vlan if segment.vlan is not None else "",
            "asset_total": total,
            "asset_active": segment.asset_active,
            "asset_unknown": segment.asset_unknown,
            "tile_w": tile_w,
            "tile_h": tile_h,
            "font_size": font_size,
            "url": f"{reverse('registry:network_map')}?segment={segment.pk}{segment_suffix}",
        }
        if segment.pk in found_segment_ids:
            data["found"] = True
        if segment.site_id:
            data["parent"] = f"site:{segment.site_id}"
        primary = primary_links.get(segment.pk)
        if primary is not None:
            data["primary_router"] = f"router:{primary[0].pk}"
        classes = []
        if sized and total == 0:
            classes.append("empty")
        if segment.pk in found_segment_ids:
            classes.append("found")
        node: dict = {"data": data}
        if classes:
            node["classes"] = " ".join(classes)
        nodes.append(node)

    router_links = router_segment_links(visible_segments)
    # Основной шлюз сегмента — роутер с минимальным интерфейсным IP (обычно .1).
    # Рисуем только его связь: остальные — дублирующие и превращают схему в паутину.
    primary_links: dict[int, tuple[RouterDevice, Segment, str, str]] = {}
    for link in router_links:
        current = primary_links.get(link[1].pk)
        if current is None or ipaddress.ip_address(link[3]) < ipaddress.ip_address(current[3]):
            primary_links[link[1].pk] = link
    primary_router_ids = {link[0].pk for link in primary_links.values()}
    # Роутеры без «своего» сегмента (все их интерфейсы — не минимальный IP в подсети)
    # иначе выглядели бы изолированными: показываем их связи пунктиром как дополнительные.
    secondary_links = [link for link in router_links if link[0].pk not in primary_router_ids]
    votes: dict[int, dict[int, int]] = {}
    for router, segment, _interface, _ip in router_links:
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

    # Граница с интернетом (SDD §5.10): default-маршруты наружу показывают шлюзы
    # («Континент» — активный и резервный) и ядро. Маршрут на наш же роутер — не граница.
    router_ips: set[str] = set()
    for router in routers:
        router_ips.add(router.host)
        for item in router.addresses or []:
            router_ips.add(str(item.get("address", "")).split("/")[0])
    gateways: dict[str, dict] = {}
    core_ids: set[int] = set()
    for router in routers:
        for route in router.routes or []:
            if route.get("dst") != "0.0.0.0/0":
                continue
            gateway_ip = str(route.get("gateway", "")).strip()
            try:
                ipaddress.ip_address(gateway_ip)
            except ValueError:
                continue  # gateway — интерфейс, значит маршрут не наружу
            if gateway_ip in router_ips:
                continue
            meta = gateways.setdefault(gateway_ip, {"routers": {}})
            meta["routers"][router.pk] = bool(route.get("active"))
            if route.get("active"):
                core_ids.add(router.pk)
    gateway_assets = {asset.ip: asset for asset in Asset.objects.filter(ip__in=list(gateways))}
    active_gateways = [ip for ip, meta in gateways.items() if any(meta["routers"].values())]
    gateways = {
        ip: meta
        for ip, meta in gateways.items()
        if ip in gateway_assets or any(_same_subnet24(ip, active) for active in active_gateways)
    }

    for router in routers:
        label = router.name or router.host
        core = router.pk in core_ids
        if core:
            label = f"{label} · ядро"
        data = {
            "id": f"router:{router.pk}",
            "label": label,
            "type": "router",
            "host": router.host,
        }
        if core:
            data["core"] = True
        if router.pk in router_site and router_site[router.pk] in {site.pk for site in sites}:
            data["parent"] = f"site:{router_site[router.pk]}"
        node: dict = {"data": data}
        if core:
            node["classes"] = "core"
        nodes.append(node)

    for router, segment, interface, _ip in primary_links.values():
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
    for router, segment, interface, _ip in secondary_links:
        if router.pk not in visible_routers:
            continue
        edges.append(
            {
                "data": {
                    "id": f"link-secondary:{router.pk}:{segment.pk}",
                    "source": f"router:{router.pk}",
                    "target": f"segment:{segment.pk}",
                    "label": interface,
                    "type": "router-segment",
                    "secondary": True,
                },
                "classes": "secondary",
            }
        )
    if gateways:
        nodes.append({"data": {"id": "edge", "label": "Граница с интернетом", "type": "edge"}})
        nodes.append(
            {"data": {"id": "internet", "label": "Интернет", "type": "internet", "parent": "edge"}}
        )
        for gateway_ip, meta in sorted(gateways.items()):
            asset = gateway_assets.get(gateway_ip)
            label = asset.hostname if asset and asset.hostname else gateway_ip
            data = {
                "id": f"gateway:{gateway_ip}",
                "label": label,
                "summary": f"{label} · {gateway_ip}",
                "type": "gateway",
                "parent": "edge",
                "ip": gateway_ip,
            }
            if asset:
                data["vendor"] = asset.mac_vendor
                if asset.segment_id:
                    data["summary"] += f" · {asset.segment.name}"
                    data["url"] = (
                        f"{reverse('registry:network_map')}?segment={asset.segment_id}{segment_suffix}"
                    )
            nodes.append({"data": data})
            is_active = any(meta["routers"].values())
            edges.append(
                {
                    "data": {
                        "id": f"wan:{gateway_ip}",
                        "source": "internet",
                        "target": f"gateway:{gateway_ip}",
                        "type": "wan",
                        "label": "активный" if is_active else "резерв",
                    },
                    **({} if is_active else {"classes": "standby"}),
                }
            )
            for router_pk, route_active in sorted(meta["routers"].items()):
                edges.append(
                    {
                        "data": {
                            "id": f"default:{router_pk}:{gateway_ip}",
                            "source": f"gateway:{gateway_ip}",
                            "target": f"router:{router_pk}",
                            "type": "default-route",
                            "label": "default" if route_active else "резерв",
                        },
                        **({} if route_active else {"classes": "standby"}),
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
                    "extra_ips": asset.extra_ips or [],
                    "mac": asset.mac,
                    "vendor": asset.mac_vendor,
                    "hostname": asset.hostname,
                    "role": effective_role(asset),
                    "os_variant": os_variant(asset),
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
                    "ping_url": reverse("registry:asset_ping", args=[asset.pk]),
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


def normalize_query(query: str) -> str:
    """«192,168,0,191», «192 168 0 191», «192.168.0.191 » → «192.168.0.191»."""
    return re.sub(r"[\s,;]+", ".", (query or "").strip()).strip(".")


# Поиск по типу устройства: точные слова (регистр не важен), а не подстроки — чтобы
# «printer-demo» искался как имя, а «принтер» — как все принтеры (SDD §5.10).
ROLE_QUERIES: dict[str, tuple[str, ...]] = {
    "workstation": (
        "арм",
        "комп",
        "компьютер",
        "пк",
        "рабочая станция",
        "ноутбук",
        "workstation",
        "pc",
    ),
    "printer": ("принтер", "мфу", "печать", "printer", "mfp"),
    "server": ("сервер", "server"),
    "phone": ("телефон", "телефоны", "ip-телефон", "voip", "phone", "sip"),
    "mobile": (
        "смартфон",
        "смартфоны",
        "мобильное устройство",
        "мобильные устройства",
        "личное устройство",
        "личные устройства",
        "mobile",
    ),
    "ap": ("точка доступа", "точки доступа", "вайфай", "wifi", "wi-fi", "тд", "ap"),
    "network": (
        "роутер",
        "маршрутизатор",
        "свитч",
        "коммутатор",
        "сетевое оборудование",
        "router",
        "switch",
        "network",
    ),
    "camera": ("камера", "видеокамера", "camera"),
    "medical": ("медицинское изделие", "медизделие", "медицина", "medical"),
    "other": ("прочее", "other"),
    "unknown": ("не определена", "неизвестно", "без роли", "unknown"),
}


def role_for_query(query: str) -> str:
    """Роль по слову-типу («принтер», «мфу», «арм», «свитч»…); "" — это не тип устройства."""
    value = (query or "").strip().lower()
    for role, words in ROLE_QUERIES.items():
        if value == role or value in words:
            return role
    return ""


OS_QUERY_WORDS = {
    "linux",
    "astra",
    "astra linux",
    "ubuntu",
    "debian",
    "red os",
    "redos",
    "centos",
    "almalinux",
    "rocky",
    "rocky linux",
    "routeros",
}

# Русские названия ОС в поиске: «астра» должна находить Astra Linux, «редос» — RED OS.
OS_QUERY_ALIASES = {
    "астра": "astra",
    "астра линукс": "astra",
    "редос": "red os",
    "ред ос": "red os",
    "убунту": "ubuntu",
    "виндовс": "windows",
    "винда": "windows",
    "линукс": "linux",
    "дебиан": "debian",
}

# Варианты фильтра по ОС — совпадают с иконками и легендой карты.
OS_FILTER_CHOICES = (
    ("windows", "Windows"),
    ("astra", "Astra Linux"),
    ("redos", "RED OS"),
    ("ubuntu", "Ubuntu"),
    ("linux", "другая Linux"),
    ("none", "не определена"),
)


def normalize_os_query(query: str) -> str:
    """Приводит русское название ОС к латинскому варианту для поиска по полям."""
    value = (query or "").strip().lower().replace("ё", "е")
    return OS_QUERY_ALIASES.get(value, value)


def os_query_q(query: str) -> Q:
    """Q для поиска по ОС с учётом русских названий и варианта «REDOS» без пробела."""
    value = normalize_os_query(query)
    condition = Q(os_name__icontains=value) | Q(os_family__icontains=value)
    if value == "red os":
        condition |= Q(os_name__icontains="redos") | Q(os_family__icontains="redos")
    return condition


def is_os_query(query: str) -> bool:
    """Похоже ли на запрос ОС: «astra», «windows», «windows 10», «server 2022».

    Для таких запросов поиск по ОС идёт раньше имён: «astra» должно найти Astra Linux,
    а не хосты с «astra» в имени; «astra-szi» остаётся поиском по имени (дефис/хвост).
    Русские названия («астра», «редос») приводятся к латинским до проверки.
    """
    value = normalize_os_query(query)
    if value in OS_QUERY_WORDS:
        return True
    if value.startswith("windows") and (len(value) == 7 or value[7] == " "):
        return True
    return bool(re.match(r"^server 20\d\d$", value))


def _overlaps(cidr: str, network: ipaddress._BaseNetwork) -> bool:
    try:
        return ipaddress.ip_network(cidr, strict=False).overlaps(network)
    except ValueError:
        return False


def search_map(query: str) -> dict:
    """Поиск на карте: тип устройства, IP (любые разделители), имя, вендор, ОС, сегмент.

    Сегменты с найденными активами подсвечиваются на графе обзора. Если IP ещё не найден
    как актив, но попадает в известную подсеть — подсвечиваем хотя бы сегмент.
    """
    raw = (query or "").strip()
    normalized = normalize_query(raw)
    assets: list[Asset] = []
    segments: list[Segment] = []
    segment_counts: list[dict] = []
    total = 0
    role_title = ""
    match = ""
    ip = None
    network = None
    role = role_for_query(raw)

    if role:
        # Тип устройства: ручная роль главнее авто — как в фильтре состава сегмента
        if role == Asset.DeviceRole.UNKNOWN:
            role_q = Q(device_role=Asset.DeviceRole.UNKNOWN, role_auto="")
        else:
            role_q = Q(device_role=role) | Q(device_role=Asset.DeviceRole.UNKNOWN, role_auto=role)
        matched = list(Asset.objects.select_related("segment").filter(role_q).order_by("ip"))
        total = len(matched)
        assets = matched[:20]
        counts: dict[int, int] = {}
        for asset in matched:
            if asset.segment_id:
                counts[asset.segment_id] = counts.get(asset.segment_id, 0) + 1
        segments = list(Segment.objects.filter(pk__in=counts).order_by("cidr"))
        segment_counts = [{"segment": segment, "count": counts[segment.pk]} for segment in segments]
        role_title = dict(Asset.DeviceRole.choices).get(role, role)
        match = "role"
        return {
            "query": raw,
            "normalized": normalized,
            "match": match,
            "role_code": role,
            "role_title": role_title,
            "total": total,
            "assets": assets,
            "segments": segments,
            "segment_counts": segment_counts,
            "segment_ids": [segment.pk for segment in segments],
        }

    if is_os_query(raw):
        # «astra», «астра», «windows 10»: ОС важнее совпадения по имени хоста
        matched_os = list(
            Asset.objects.select_related("segment").filter(os_query_q(raw)).order_by("ip")
        )
        if matched_os:
            counts: dict[int, int] = {}
            for asset in matched_os:
                if asset.segment_id:
                    counts[asset.segment_id] = counts.get(asset.segment_id, 0) + 1
            os_segments = list(Segment.objects.filter(pk__in=counts).order_by("cidr"))
            return {
                "query": raw,
                "normalized": normalized,
                "match": "os",
                "role_code": "",
                "role_title": "",
                "total": len(matched_os),
                "assets": matched_os[:20],
                "segments": os_segments,
                "segment_counts": [
                    {"segment": segment, "count": counts[segment.pk]} for segment in os_segments
                ],
                "segment_ids": [segment.pk for segment in os_segments],
            }

    if normalized:
        try:
            ip = ipaddress.ip_address(normalized)
        except ValueError:
            try:
                network = ipaddress.ip_network(normalized, strict=False)
            except ValueError:
                network = None

    if ip is not None:
        assets = list(
            Asset.objects.select_related("segment").filter(
                Q(ip=str(ip)) | Q(extra_ips__contains=[str(ip)])
            )[:20]
        )
        if assets:
            match = "ip"
    elif network is not None:
        segments = [s for s in Segment.objects.all() if _overlaps(s.cidr, network)]
        if segments:
            match = "subnet"
    elif normalized:
        # Сначала IP: «191» — это *.191, «168.0» — любой октет с .168.0., «192.168» — префикс.
        # Имя актива — только если по IP ничего нет, и с пометкой «по имени».
        ip_like = (
            Q(ip__startswith=normalized)
            | Q(ip__endswith=f".{normalized}")
            | Q(ip__contains=f".{normalized}.")
        )
        assets = list(Asset.objects.select_related("segment").filter(ip_like).order_by("ip")[:20])
        if assets:
            match = "ip"
        else:
            assets = list(
                Asset.objects.select_related("segment")
                .filter(hostname__icontains=raw)
                .order_by("ip")[:20]
            )
            if assets:
                match = "name"
        if not assets:
            # Вендор («new platforms» → Континенты, «hp» → печать)
            assets = list(
                Asset.objects.select_related("segment")
                .filter(mac_vendor__icontains=raw)
                .order_by("ip")[:20]
            )
            if assets:
                match = "vendor"
        if not assets:
            # ОС из nmap: «windows», «linux», «windows 10», «астра», «редос»
            assets = list(
                Asset.objects.select_related("segment").filter(os_query_q(raw)).order_by("ip")[:20]
            )
            if assets:
                match = "os"

    if assets:
        ids = {asset.segment_id for asset in assets if asset.segment_id}
        segments = list(Segment.objects.filter(pk__in=ids).order_by("cidr"))
    elif ip is not None and not segments:
        # IP известен, актива ещё нет — подсветим хотя бы подсеть, в которую он попадает
        for segment in Segment.objects.all():
            try:
                if ip in ipaddress.ip_network(segment.cidr, strict=False):
                    segments.append(segment)
                    match = "subnet"
            except ValueError:
                continue

    if not assets and not segments and raw:
        segments = list(
            Segment.objects.filter(Q(name__icontains=raw) | Q(cidr__icontains=normalized)).order_by(
                "cidr"
            )[:20]
        )
        if segments:
            match = "segment"
    return {
        "query": raw,
        "normalized": normalized,
        "match": match,
        "role_code": "",
        "role_title": "",
        "total": 0,
        "assets": assets,
        "segments": segments,
        "segment_counts": segment_counts,
        "segment_ids": [segment.pk for segment in segments],
    }
