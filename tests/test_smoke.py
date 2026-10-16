"""Smoke недели 1: логин-страница, редирект анонима, доступность дашборда."""

from __future__ import annotations

import pytest


def test_login_page_renders(client):
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    assert "Вход" in response.content.decode()


def test_root_redirects_anonymous_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


def test_dashboard_available_after_login(login, make_user):
    user = make_user(role="ib_officer")
    client = login(user)

    response = client.get("/")

    assert response.status_code == 200
    assert "Дашборд" in response.content.decode()


@pytest.mark.django_db
def test_static_vendor_assets_exist(settings):
    for asset in (
        "vendor/bootstrap.min.css",
        "vendor/bootstrap.bundle.min.js",
        "vendor/htmx.min.js",
        "vendor/alpine.min.js",
    ):
        path = settings.STATICFILES_DIRS[0] / asset
        assert path.is_file(), f"нет вендорного ассета: {asset}"
        assert path.stat().st_size > 10_000
