"""Реестр (SDD §3.1): площадки, сегменты (network scopes), люди, активы, дрейф активов."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.registry.validators import validate_cidr


def default_scan_window() -> dict:
    """Ночное окно по умолчанию (SDD §5.2), все дни недели."""
    return {"days": [0, 1, 2, 3, 4, 5, 6], "start": "23:00", "end": "05:00"}


class Site(models.Model):
    name = models.CharField("название", max_length=120, unique=True)
    address = models.CharField("адрес", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "Площадка"
        verbose_name_plural = "Площадки"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Person(models.Model):
    fio = models.CharField("ФИО", max_length=200)
    position = models.CharField("должность", max_length=150, blank=True, default="")
    phone = models.CharField("телефон", max_length=50, blank=True, default="")
    email = models.EmailField("почта", blank=True, default="")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="учётная запись",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="person",
    )

    class Meta:
        verbose_name = "Человек"
        verbose_name_plural = "Люди"
        ordering = ["fio"]

    def __str__(self) -> str:
        return self.fio


class Segment(models.Model):
    """Network scope: только сегменты отсюда попадают в discovery."""

    class ScanProfile(models.TextChoices):
        PING = "ping", "только ping-sweep"
        TOP100 = "top100", "top-100 портов"

    site = models.ForeignKey(
        Site, verbose_name="площадка", on_delete=models.PROTECT, related_name="segments"
    )
    name = models.CharField("название", max_length=120)
    cidr = models.CharField("подсеть", max_length=43, unique=True, validators=[validate_cidr])
    vlan = models.PositiveSmallIntegerField("VLAN", null=True, blank=True)
    description = models.TextField("описание", blank=True, default="")
    owner_person = models.ForeignKey(
        Person,
        verbose_name="ответственный",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="segments",
    )
    scan_enabled = models.BooleanField("скан разрешён", default=False)
    scan_profile = models.CharField(
        "профиль скана", max_length=10, choices=ScanProfile.choices, default=ScanProfile.PING
    )
    scan_window = models.JSONField("окно скана", default=default_scan_window)
    last_scan_at = models.DateTimeField("последний скан", null=True, blank=True)

    class Meta:
        verbose_name = "Сегмент"
        verbose_name_plural = "Сегменты (network scopes)"
        ordering = ["site__name", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.cidr})"


class Asset(models.Model):
    """Актив, обнаруженный коллектором. Идентичность: сначала MAC, затем IP (SDD §5.2)."""

    class DeviceRole(models.TextChoices):
        SERVER = "server", "сервер"
        WORKSTATION = "workstation", "АРМ"
        NETWORK = "network", "сетевое оборудование"
        MEDICAL = "medical", "медицинское изделие"
        PRINTER = "printer", "печать/МФУ"
        OTHER = "other", "прочее"
        UNKNOWN = "unknown", "не определена"

    class Criticality(models.TextChoices):
        LOW = "low", "низкая"
        MEDIUM = "medium", "средняя"
        HIGH = "high", "высокая"

    class Source(models.TextChoices):
        NMAP = "nmap", "nmap"
        ICMP = "icmp", "ICMP sweep"
        MIKROTIK_SNMP = "mikrotik_snmp", "Mikrotik SNMP"
        MIKROTIK_API = "mikrotik_api", "Mikrotik API"
        MANUAL = "manual", "вручную"

    ip = models.GenericIPAddressField("IP", protocol="IPv4", db_index=True)
    # shortcut: IP не уникален — после переиспользования IP в истории остаются закрытый
    # и новый актив; «активный» = miss_count < MISS_THRESHOLD. При нескольких воркерах
    # скана — partial unique index.
    mac = models.CharField("MAC", max_length=17, blank=True, default="")
    hostname = models.CharField("имя хоста", max_length=255, blank=True, default="")
    os_family = models.CharField("семейство ОС", max_length=50, blank=True, default="")
    os_name = models.CharField("ОС", max_length=120, blank=True, default="")
    site = models.ForeignKey(
        Site,
        verbose_name="площадка",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    segment = models.ForeignKey(
        Segment,
        verbose_name="сегмент",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    device_role = models.CharField(
        "роль", max_length=20, choices=DeviceRole.choices, default=DeviceRole.UNKNOWN
    )
    criticality = models.CharField(
        "критичность", max_length=10, choices=Criticality.choices, default=Criticality.LOW
    )
    discovery_source = models.CharField(
        "источник", max_length=20, choices=Source.choices, default=Source.NMAP
    )
    ports = models.JSONField("открытые порты", default=list, blank=True)
    fingerprint = models.JSONField("отпечаток", default=dict, blank=True)
    owner_person = models.ForeignKey(
        Person,
        verbose_name="владелец",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    first_seen_at = models.DateTimeField("первое обнаружение", auto_now_add=True)
    last_seen_at = models.DateTimeField("последнее обнаружение", db_index=True)
    # промахи подряд для анти-мигания: «пропал» — после 3 (SDD §5.2)
    miss_count = models.PositiveSmallIntegerField("промахов подряд", default=0)

    class Meta:
        verbose_name = "Актив"
        verbose_name_plural = "Активы"
        ordering = ["ip"]
        indexes = [models.Index(fields=["segment", "last_seen_at"])]

    def __str__(self) -> str:
        return f"{self.ip} {self.hostname}".strip()


class AssetEvent(models.Model):
    """Журнал дрейфа активов (SDD §3.1)."""

    class Kind(models.TextChoices):
        NEW = "new", "обнаружен"
        DISAPPEARED = "disappeared", "пропал"
        CHANGED = "changed", "изменился"
        PORTS_CHANGED = "ports_changed", "изменились порты"

    asset = models.ForeignKey(
        Asset, verbose_name="актив", on_delete=models.CASCADE, related_name="events"
    )
    kind = models.CharField("тип", max_length=20, choices=Kind.choices)
    at = models.DateTimeField("время", auto_now_add=True, db_index=True)
    details = models.JSONField("детали", default=dict, blank=True)

    class Meta:
        verbose_name = "Событие актива"
        verbose_name_plural = "События активов (дрейф)"
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.asset_id} {self.kind}"
