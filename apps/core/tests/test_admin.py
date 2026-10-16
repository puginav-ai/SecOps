"""Админка: пользователи и read-only журнал аудита."""

from __future__ import annotations

import pytest

from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def test_admin_pages_load_for_superuser(client, make_user):
    admin = make_user("root2", is_superuser=True, is_staff=True)
    client.force_login(admin)

    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/core/auditlog/").status_code == 200
    assert client.get("/admin/core/user/").status_code == 200


def test_audit_admin_is_read_only(client, make_user):
    admin = make_user("root3", is_superuser=True, is_staff=True)
    AuditLog.write(action="test", actor=admin)
    client.force_login(admin)

    assert client.get("/admin/core/auditlog/add/").status_code == 403
