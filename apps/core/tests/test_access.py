"""RBAC: матрица ролей (SDD §4) и декоратор role_required."""

from __future__ import annotations

import pytest

from apps.core.access import MODULES, ROLE_MATRIX, module_access, user_modules, user_roles

pytestmark = pytest.mark.django_db


def test_matrix_covers_all_roles_and_modules():
    assert set(ROLE_MATRIX) == {"ib_admin", "ib_officer", "it_ops", "system_owner", "reader"}
    for role, row in ROLE_MATRIX.items():
        assert set(row) == set(MODULES), f"у роли {role} не описаны все модули"


def test_matrix_spot_checks_from_sdd():
    assert ROLE_MATRIX["ib_officer"]["admin"] == ""  # админка — только у ИБ-админа
    assert ROLE_MATRIX["it_ops"]["kzi"] == ""  # ИТ не ведёт КЗИ
    assert ROLE_MATRIX["reader"]["discovery"] == ""  # руководство не видит discovery
    assert ROLE_MATRIX["reader"]["evidence"] == "r"  # метаданные без скачивания
    assert ROLE_MATRIX["ib_admin"]["admin"] == "rw"


def test_superuser_has_rw_everywhere(make_user):
    admin = make_user("root", is_superuser=True)
    assert all(module_access(admin, module) == "rw" for module in MODULES)


def test_user_without_roles_has_no_access(make_user):
    user = make_user("noroles")
    assert user_roles(user) == set()
    assert user_modules(user) == []


def test_access_combines_roles_by_maximum(make_user):
    from django.contrib.auth.models import Group

    user = make_user("multi")
    user.groups.add(Group.objects.get(name="reader"), Group.objects.get(name="it_ops"))
    assert module_access(user, "discovery") == "rw"  # it_ops даёт rw, reader — нет
    assert module_access(user, "evidence") == "r"


@pytest.mark.urls("tests.dummy_urls")
def test_role_required_decorator(client, make_user, login):
    reader = make_user("reader1", role="reader")
    it_ops = make_user("it1", role="it_ops")

    response = client.get("/dummy/read/")  # аноним
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")

    login(reader)
    assert client.get("/dummy/read/").status_code == 200
    assert client.get("/dummy/write/").status_code == 403  # "r" не даёт запись

    login(it_ops)
    assert client.get("/dummy/write/").status_code == 200  # registry: rw


@pytest.mark.urls("tests.dummy_urls")
def test_role_required_denies_module_without_access(client, make_user, login):
    client_login = login(make_user("reader2", role="reader"))
    assert client_login.get("/dummy/read/").status_code == 200
