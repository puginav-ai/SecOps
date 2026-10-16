"""URL уведомлений."""

from __future__ import annotations

from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.my_notifications, name="list"),
]
