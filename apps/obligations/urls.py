"""URL обязательств."""

from __future__ import annotations

from django.urls import path

from apps.obligations import views

app_name = "obligations"

urlpatterns = [
    path("", views.obligation_list, name="list"),
    path("<int:pk>/close/", views.obligation_close, name="close"),
    path("<int:pk>/cancel/", views.obligation_cancel, name="cancel"),
]
