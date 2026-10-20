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
    path("assets/unknown/", views.unknown_assets, name="unknown_assets"),
    path("assets/<int:pk>/ping/", views.asset_ping, name="asset_ping"),
    path("map/", views.network_map, name="network_map"),
    path("map/assets.xlsx", views.segment_assets_xlsx, name="segment_assets_xlsx"),
    path("segments/<int:pk>/scan-now/", views.segment_scan_now, name="segment_scan_now"),
    path("systems/", views.system_list, name="system_list"),
    path("systems/new/", views.system_create, name="system_create"),
    path("systems/<int:pk>/", views.system_detail, name="system_detail"),
    path("systems/<int:pk>/edit/", views.system_edit, name="system_edit"),
    path("systems/<int:pk>/components/add/", views.component_add, name="component_add"),
    path(
        "systems/<int:pk>/components/<int:component_id>/delete/",
        views.component_remove,
        name="component_remove",
    ),
    path("persons/", views.person_list, name="person_list"),
    path("persons/new/", views.person_create, name="person_create"),
    path("persons/<int:pk>/edit/", views.person_edit, name="person_edit"),
]
