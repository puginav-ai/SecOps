"""Общие фикстуры: пользователи с ролями (вымышленные данные)."""

from __future__ import annotations

import pytest

TEST_PASSWORD = "test-password-12"


@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import Group

    from apps.core.models import User

    def _make(username: str = "user", role: str | None = None, **extra):
        user = User.objects.create_user(username=username, password=TEST_PASSWORD, **extra)
        if role:
            user.groups.add(Group.objects.get(name=role))
        return user

    return _make


@pytest.fixture
def login(client):
    def _login(user):
        assert client.login(username=user.username, password=TEST_PASSWORD)
        return client

    return _login
