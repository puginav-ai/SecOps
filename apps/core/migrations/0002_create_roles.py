"""Роли RBAC как группы (SDD §4).

Список заморожен в миграции осознанно: код приложения (apps.core.access) может меняться,
история миграций — нет.
"""

from __future__ import annotations

from django.db import migrations

ROLES = ("ib_admin", "ib_officer", "it_ops", "system_owner", "reader")


def create_roles(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    for name in ROLES:
        group_model.objects.get_or_create(name=name)


def remove_roles(apps, schema_editor):
    group_model = apps.get_model("auth", "Group")
    group_model.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_roles, remove_roles),
    ]
