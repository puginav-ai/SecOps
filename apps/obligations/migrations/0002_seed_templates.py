"""Стартовые шаблоны обязательств (SDD §3.5). Идемпотентна."""

from __future__ import annotations

from django.db import migrations

# (kind, name, RRULE, lead_days, policy, requires_evidence, owner_role)
TEMPLATES = [
    (
        "kzi",
        "Оценка КЗИ",
        "FREQ=MONTHLY;INTERVAL=6",
        [30, 7, 1],
        [
            {"step": 1, "after_days": 7, "recipients": [{"role": "ib_admin"}]},
            {"step": 2, "after_days": 30, "recipients": [{"role": "ib_officer"}]},
        ],
        True,
        "ib_admin",
    ),
    ("pzi", "Оценка ПЗИ", "FREQ=YEARLY;INTERVAL=2", [60, 30, 7], [], True, "ib_admin"),
    (
        "report",
        "Отчёт после оценки (SLA 5 рабочих дней)",
        "",
        [5, 2, 1],
        [{"step": 1, "after_days": 2, "recipients": [{"role": "ib_admin"}]}],
        True,
        "ib_officer",
    ),
    ("report", "Доведение результатов до руководителя (3 дня)", "", [3, 1], [], False, "ib_admin"),
    ("contract", "Пересмотр договоров и assurance", "FREQ=YEARLY;INTERVAL=1", [60, 30, 7], [], True, "ib_admin"),
    ("contract", "Получить assurance pack (ЛИС/PACS/хостинг/МИС/ЗУП)", "FREQ=YEARLY;INTERVAL=1", [45, 14, 3], [], True, "ib_officer"),
    (
        "fstec_reply",
        "Контроль ответа ФСТЭК (по исходящему письму)",
        "",
        [10, 5, 1],
        [{"step": 1, "after_days": 3, "recipients": [{"role": "ib_admin"}]}],
        True,
        "ib_officer",
    ),
    (
        "backup",
        "Проверка восстановления резервных копий",
        "FREQ=MONTHLY;INTERVAL=1",
        [7, 3, 1],
        [{"step": 1, "after_days": 3, "recipients": [{"role": "it_ops"}]}],
        True,
        "it_ops",
    ),
    ("telemedicine", "Телемедицина: уточнить модель владения", "", [30, 7, 1], [], False, "ib_admin"),
    ("update", "Обновление ПО и зеркал обновлений", "FREQ=MONTHLY;INTERVAL=3", [14, 7, 1], [], True, "it_ops"),
]


def seed_templates(apps, schema_editor) -> None:
    template_model = apps.get_model("obligations", "ObligationTemplate")
    for kind, name, rule, lead, policy, requires_evidence, owner_role in TEMPLATES:
        template_model.objects.get_or_create(
            kind=kind,
            name=name,
            defaults={
                "recurrence_rule": rule,
                "lead_days": lead,
                "escalation_policy": policy,
                "requires_closing_evidence": requires_evidence,
                "owner_role": owner_role,
            },
        )


def unseed_templates(apps, schema_editor) -> None:
    template_model = apps.get_model("obligations", "ObligationTemplate")
    instance_model = apps.get_model("obligations", "ObligationInstance")
    for _kind, name, *_rest in TEMPLATES:
        instance_model.objects.filter(template__name=name).delete()
        template_model.objects.filter(name=name).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("obligations", "0001_initial"),
        ("notifications", "0002_initial"),
    ]
    operations = [migrations.RunPython(seed_templates, unseed_templates)]
