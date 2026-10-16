"""Корневые url: admin, auth (login/logout), UI ядра. API /api/v1/ появится с модулями."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("registry/", include("apps.registry.urls")),
    path("compliance/", include("apps.compliance.urls")),
    path("evidence/", include("apps.evidence.urls")),
    path("", include("apps.core.urls")),
]
