"""Стартовый каталог KPI для КЗИ (SDD §3.4; пороги и состав уточняются по Приложению В №10).
Идемпотентна."""

from __future__ import annotations

from django.db import migrations

GROUPS = [
    ("ORG", "Организация работ", "0.2000", 1),
    ("ACC", "Управление доступом", "0.3000", 2),
    ("PROT", "Защита информации", "0.3000", 3),
    ("MON", "Мониторинг и контроль", "0.2000", 4),
]

# (группа, код, название, максимум, вес, обязательный, порядок)
ITEMS = [
    ("ORG", "ORG-DOC", "Приказы и регламенты по ИБ", "1.00", "1.0000", True, 1),
    ("ORG", "ORG-TRAIN", "Обучение и инструктажи персонала", "1.00", "1.0000", False, 2),
    ("ORG", "ORG-SKZI", "Учёт СКЗИ и ключевых документов", "1.00", "1.0000", False, 3),
    ("ACC", "ACC-PWD", "Парольная и учётная политика", "1.00", "1.0000", True, 1),
    ("ACC", "ACC-ROLE", "Разграничение прав доступа", "1.00", "1.0000", True, 2),
    ("ACC", "ACC-REVOKE", "Отзыв доступов (увольнения, переводы)", "1.00", "1.0000", False, 3),
    ("PROT", "PROT-AV", "Антивирусная защита", "1.00", "1.0000", True, 1),
    ("PROT", "PROT-PATCH", "Управление обновлениями", "1.00", "1.0000", True, 2),
    ("PROT", "PROT-CRYPTO", "Криптографическая защита каналов", "1.00", "1.0000", False, 3),
    ("MON", "MON-LOG", "Журналирование событий", "1.00", "1.0000", False, 1),
    ("MON", "MON-SCAN", "Контроль сети и уязвимостей", "1.00", "1.0000", False, 2),
]


def seed_kpi(apps, schema_editor) -> None:
    group_model = apps.get_model("kzi", "KpiGroup")
    item_model = apps.get_model("kzi", "KpiItem")
    for code, name, weight, sort in GROUPS:
        group_model.objects.get_or_create(
            code=code, defaults={"name": name, "weight_rj": weight, "sort": sort}
        )
    for group_code, code, name, max_value, weight, mandatory, sort in ITEMS:
        item_model.objects.get_or_create(
            code=code,
            defaults={
                "group": group_model.objects.get(code=group_code),
                "name": name,
                "max_value": max_value,
                "weight": weight,
                "is_mandatory": mandatory,
                "sort": sort,
            },
        )


def unseed_kpi(apps, schema_editor) -> None:
    item_model = apps.get_model("kzi", "KpiItem")
    group_model = apps.get_model("kzi", "KpiGroup")
    item_model.objects.filter(code__in=[item[1] for item in ITEMS]).delete()
    group_model.objects.filter(code__in=[group[0] for group in GROUPS]).delete()


class Migration(migrations.Migration):
    dependencies = [("kzi", "0001_initial")]
    operations = [migrations.RunPython(seed_kpi, unseed_kpi)]
