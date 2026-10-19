"""Стартовый справочник правил стадий инцидентов (SDD §3.6). Идемпотентна."""

from __future__ import annotations

from django.db import migrations

# (kind, stage_code, offset_minutes, target, template_code, applies_if, note)
RULES = [
    (
        "kii",
        "1h",
        60,
        "ib_admin",
        "Срочно: инцидент КИИ — доложить руководству",
        {"kii_scope": "yes"},
        "Стадия «1 час» (только КИИ)",
    ),
    ("", "T1", 240, "ib_admin", "T1: локализовать инцидент", {}, "Первичная локализация — 4 часа"),
    ("", "T2", 1440, "ib_officer", "T2: завершить разбор и уведомления", {}, "Разбор — 24 часа"),
    (
        "kii",
        "regulator_24",
        1440,
        "regulator",
        "Уведомить регулятора об инциденте КИИ (24 часа)",
        {"kii_scope": "yes"},
        "Внешнее уведомление, evidence обязательно",
    ),
    (
        "pdn",
        "pdn_24",
        1440,
        "regulator",
        "Уведомить Роскомнадзор об утечке ПДн (24 часа)",
        {},
        "Внешнее уведомление, evidence обязательно",
    ),
]


def seed_rules(apps, schema_editor) -> None:
    rule_model = apps.get_model("incidents", "IncidentNotificationRule")
    for kind, stage_code, offset, target, template, applies_if, note in RULES:
        rule_model.objects.get_or_create(
            stage_code=stage_code,
            target=target,
            defaults={
                "kind": kind,
                "offset_minutes": offset,
                "template_code": template,
                "applies_if": applies_if,
                "note": note,
            },
        )


def unseed_rules(apps, schema_editor) -> None:
    rule_model = apps.get_model("incidents", "IncidentNotificationRule")
    stage_model = apps.get_model("incidents", "IncidentNotification")
    codes = [rule[1] for rule in RULES]
    stage_model.objects.filter(stage_code__in=codes).delete()
    rule_model.objects.filter(stage_code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [("incidents", "0001_initial")]
    operations = [migrations.RunPython(seed_rules, unseed_rules)]
