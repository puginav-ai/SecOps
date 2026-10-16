"""Начальный набор ИС больницы (SDD §5.1, неделя 3). Идемпотентна."""

from __future__ import annotations

from django.db import migrations

# (название, тип, доп. примечание)
SYSTEMS = [
    ("ЛИС", "lis", ""),
    ("PACS", "pacs", ""),
    ("Аптека", "pharmacy", ""),
    ("Сайт", "site", ""),
    ("МИС", "mis", ""),
    ("ЗУП", "zup", ""),
    ("ВКС", "vks", ""),
    ("Телемедицина", "telemedicine", "ПДн/КИИ — неизвестно: обязательство «уточнить» (SDD §3.1)."),
    ("Инфраструктура", "infrastructure", ""),
]

NOTE = "Владелец и контроль — уточнить (Приложение В №11)."


def seed_systems(apps, schema_editor) -> None:
    system_model = apps.get_model("registry", "System")
    for name, system_type, extra in SYSTEMS:
        notes = f"{NOTE} {extra}".strip()
        system_model.objects.get_or_create(
            name=name, system_type=system_type, defaults={"notes": notes}
        )


def unseed_systems(apps, schema_editor) -> None:
    system_model = apps.get_model("registry", "System")
    for name, system_type, _ in SYSTEMS:
        system_model.objects.filter(name=name, system_type=system_type).delete()


class Migration(migrations.Migration):
    dependencies = [("registry", "0002_system_systemcomponent")]
    operations = [migrations.RunPython(seed_systems, unseed_systems)]
