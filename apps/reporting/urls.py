"""URL отчётности."""

from __future__ import annotations

from django.urls import path

from apps.reporting import views

app_name = "reporting"

urlpatterns = [
    path("", views.reports_index, name="index"),
    path("management/", views.management_report, name="management"),
    path("gaps.csv", views.gaps_csv, name="gaps_csv"),
    path("gaps.xlsx", views.gaps_xlsx, name="gaps_xlsx"),
    path("overdue.csv", views.overdue_csv, name="overdue_csv"),
    path("overdue.xlsx", views.overdue_xlsx, name="overdue_xlsx"),
    path("evidence.xlsx", views.evidence_xlsx, name="evidence_xlsx"),
    path("unknown-assets.xlsx", views.unknown_xlsx, name="unknown_xlsx"),
    path("kzi.xlsx", views.kzi_xlsx, name="kzi_xlsx"),
]
