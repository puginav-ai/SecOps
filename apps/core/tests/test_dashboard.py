"""Дашборд: разделы зависят от роли (SDD §4)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_reader_sees_registry_but_not_discovery(login, make_user):
    client = login(make_user("reader", role="reader"))

    body = client.get("/").content.decode()

    assert "Реестр ИС/активов" in body
    assert "Discovery" not in body


def test_ib_admin_sees_every_module_but_not_without_roles(login, make_user):
    client = login(make_user("boss", role="ib_admin"))

    body = client.get("/").content.decode()

    for title in ("Discovery", "КЗИ/ПЗИ", "Инциденты", "Администрирование"):
        assert title in body


def test_user_without_roles_sees_empty_state(login, make_user):
    client = login(make_user("nobody"))

    body = client.get("/").content.decode()

    assert "не назначены" in body
    assert "Discovery" not in body
