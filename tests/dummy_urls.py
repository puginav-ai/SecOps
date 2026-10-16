"""Тестовый URLconf для проверки декоратора role_required (нигде не подключён)."""

from __future__ import annotations

from django.http import HttpResponse
from django.urls import path

from apps.core.access import role_required


@role_required("registry")
def registry_read(request):
    return HttpResponse("read-ok")


@role_required("registry", "rw")
def registry_write(request):
    return HttpResponse("write-ok")


urlpatterns = [
    path("dummy/read/", registry_read),
    path("dummy/write/", registry_write),
]
