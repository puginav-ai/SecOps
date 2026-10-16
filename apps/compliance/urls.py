"""URL контролей и проверок."""

from __future__ import annotations

from django.urls import path

from apps.compliance import views

app_name = "compliance"

urlpatterns = [
    path("", views.matrix, name="matrix"),
    path("catalog/", views.catalog, name="catalog"),
    path("implementations/<int:pk>/edit/", views.implementation_edit, name="implementation_edit"),
    path("implementations/<int:pk>/test/", views.test_run_create, name="test_run_create"),
]
