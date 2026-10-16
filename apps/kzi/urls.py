"""URL КЗИ."""

from __future__ import annotations

from django.urls import path

from apps.kzi import views

app_name = "kzi"

urlpatterns = [
    path("", views.assessment_list, name="list"),
    path("new/", views.assessment_create, name="create"),
    path("<int:pk>/", views.assessment_detail, name="detail"),
    path("<int:pk>/values/", views.assessment_save_values, name="save_values"),
    path("<int:pk>/close/", views.assessment_close, name="close"),
]
