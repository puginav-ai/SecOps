"""Инвентарь роутеров: имя и адреса интерфейсов для связей карты (SDD §5.10)."""

from __future__ import annotations

import pytest

from apps.discovery import tasks
from apps.discovery.models import RouterDevice
from collector.mikrotik import RouterData, normalized_addresses

pytestmark = pytest.mark.django_db


@pytest.fixture
def router_settings(settings):
    settings.MIKROTIK_HOST = "10.0.0.1"
    settings.MIKROTIK_API_USER = "collector"
    settings.MIKROTIK_API_PASSWORD = "not-a-real-secret"  # noqa: S105 — вымышленное значение
    settings.MIKROTIK_API_SSL = False
    settings.MIKROTIK_EXTRA_ROUTERS = []
    return settings


def test_normalized_addresses_skip_disabled_invalid_and_broken():
    rows = [
        {"address": "10.0.2.1/24", "interface": "bridge", "disabled": False},
        {"address": "192.168.110.2/24", "interface": "sfp10", "disabled": "true"},
        {"address": "172.16.10.1/24", "interface": "ether2", "invalid": "true"},
        {"address": "не-адрес", "interface": "ether1"},
    ]

    assert normalized_addresses(rows) == [
        {"address": "10.0.2.1/24", "interface": "bridge", "network": "10.0.2.0/24"}
    ]


def test_refresh_inventory_upserts_router(monkeypatch, router_settings) -> None:
    monkeypatch.setattr(
        tasks,
        "fetch_router_data",
        lambda *args, **kwargs: RouterData(
            identity="MT-Root",
            addresses=({"address": "10.0.2.1/24", "interface": "bridge"},),
        ),
    )

    assert tasks.refresh_router_inventory() == 1

    router = RouterDevice.objects.get(host="10.0.0.1")
    assert router.name == "MT-Root"
    assert router.addresses == [
        {"address": "10.0.2.1/24", "interface": "bridge", "network": "10.0.2.0/24"}
    ]


def test_unavailable_router_does_not_break_the_rest(monkeypatch, router_settings) -> None:
    router_settings.MIKROTIK_EXTRA_ROUTERS = [
        {"host": "10.0.0.2", "user": "collector", "password": "test-only"}
    ]

    def fake_fetch(host, *args, **kwargs):
        if host == "10.0.0.2":
            return RouterData(identity="MT-Pol", addresses=())
        raise TimeoutError("router is down")

    monkeypatch.setattr(tasks, "fetch_router_data", fake_fetch)

    assert tasks.refresh_router_inventory() == 1
    assert RouterDevice.objects.get().name == "MT-Pol"
