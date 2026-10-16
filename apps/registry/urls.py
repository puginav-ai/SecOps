"""URL реестра."""

from __future__ import annotations

from django.urls import path

from apps.registry import views

app_name = "registry"

urlpatterns = [
    path("", views.segment_list, name="segment_list"),
    path("segments/new/", views.segment_create, name="segment_create"),
    path("segments/<int:pk>/edit/", views.segment_edit, name="segment_edit"),
    path("segments/<int:pk>/delete/", views.segment_delete, name="segment_delete"),
    path("assets/", views.asset_list, name="asset_list"),
]
