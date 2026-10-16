"""URL отчётности."""

from __future__ import annotations

from django.urls import path

from apps.reporting import views

app_name = "reporting"

urlpatterns = [
    path("", views.reports_index, name="index"),
    path("gaps.csv", views.gaps_csv, name="gaps_csv"),
    path("overdue.csv", views.overdue_csv, name="overdue_csv"),
]
