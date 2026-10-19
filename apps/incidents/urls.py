"""URL инцидентов."""

from __future__ import annotations

from django.urls import path

from apps.incidents import views

app_name = "incidents"

urlpatterns = [
    path("", views.incident_list, name="list"),
    path("new/", views.incident_create, name="create"),
    path("<int:pk>/", views.incident_detail, name="detail"),
    path("<int:pk>/status/", views.incident_status, name="status"),
    path("<int:pk>/close/", views.incident_close, name="close"),
    path("<int:pk>/stages/<int:stage_id>/send/", views.stage_send, name="stage_send"),
]
