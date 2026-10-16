"""URL evidence."""

from __future__ import annotations

from django.urls import path

from apps.evidence import views

app_name = "evidence"

urlpatterns = [
    path("", views.evidence_list, name="list"),
    path("upload/", views.evidence_upload, name="upload"),
    path("expiring/", views.evidence_expiring, name="expiring"),
    path("<int:pk>/", views.evidence_detail, name="detail"),
    path("<int:pk>/download/", views.evidence_download, name="download"),
    path("<int:pk>/link/", views.evidence_link_add, name="link_add"),
]
