"""Стартовый каталог: НПА → требования → контроли → проверки (SDD §5.3, неделя 4).

Состав верхнеуровневый; конкретику уточняем на пилоте. Миграция идемпотентна.
"""

from __future__ import annotations

from django.db import migrations

ACTS = [
    ("117-ФЗ «О безопасности КИИ»", "2017"),
    ("152-ФЗ «О персональных данных»", ""),
    ("Приказы ФСТЭК России (СКЗИ)", ""),
    ("Регламенты эксплуатации СКЗИ", ""),
]

REQUIREMENTS = [
    (
        "117-ФЗ «О безопасности КИИ»",
        "ст. 7",
        "kii",
        "Категорирование объектов КИИ и ведение перечня значимых объектов",
    ),
    (
        "117-ФЗ «О безопасности КИИ»",
        "ст. 9",
        "kii",
        "Создание системы безопасности значимого объекта, меры по обеспечению безопасности",
    ),
    (
        "117-ФЗ «О безопасности КИИ»",
        "ст. 10",
        "kii",
        "Оценка защищённости значимых объектов и реагирование на результаты оценки",
    ),
    (
        "152-ФЗ «О персональных данных»",
        "ст. 18.1",
        "pdn",
        "Учёт носителей персональных данных и машинных носителей, меры контроля",
    ),
    (
        "152-ФЗ «О персональных данных»",
        "ст. 19",
        "pdn",
        "Принятие правовых, организационных и технических мер по обеспечению безопасности ПДн",
    ),
    (
        "152-ФЗ «О персональных данных»",
        "ст. 22.1",
        "pdn",
        "Уведомления Роскомнадзора; обезличивание и обработка без средств идентификации",
    ),
    (
        "Приказы ФСТЭК России (СКЗИ)",
        "п. 5",
        "skzi",
        "Поэтапный учёт СКЗИ, ключевых документов и их хранения",
    ),
    (
        "Приказы ФСТЭК России (СКЗИ)",
        "п. 6",
        "skzi",
        "Регламенты криптографической защиты информации и контроль их исполнения",
    ),
    (
        "Регламенты эксплуатации СКЗИ",
        "р. 1",
        "skzi",
        "Периодический контроль эксплуатации СКЗИ и условий применения",
    ),
]

CONTROLS = [
    ("KII-CAT", "Категорирование и перечень объектов КИИ", "kii", "Перечень значимых объектов, категории, заявления."),
    ("KII-SEC", "Система безопасности значимого объекта", "kii", "Организационные и технические меры СБ ЗО."),
    ("ASSET", "Учёт активов и сетевых сегментов", "other", "Реестр активов, ответственные, drift-контроль."),
    ("ACCESS", "Управление доступом и парольная политика", "other", "Учётные записи, права, пароли, блокировки."),
    ("PDN-ACC", "Разграничение доступа к ПДн", "pdn", "Роли и допуски к системам, обрабатывающим ПДн."),
    ("BACKUP", "Резервное копирование и восстановление", "other", "Расписание, хранение, тестовые восстановления."),
    ("ANTIVIR", "Антивирусная защита", "other", "Покрытие АРМ/серверов, актуальность баз, реакция."),
    ("PATCH", "Обновление ПО и управление уязвимостями", "other", "Сроки установки критических обновлений."),
    ("LOGGING", "Журналирование и аудит событий", "other", "Сбор, хранение и анализ журналов, аудит-след."),
    ("SKZI-ACC", "Учёт и контроль эксплуатации СКЗИ", "skzi", "Журналы учёта СКЗИ, поверки, условия эксплуатации."),
    ("SKZI-NET", "Шифрование каналов связи (СКЗИ)", "skzi", "Защищённые каналы для ПДн и обмена с внешними контурами."),
    ("REMOTE", "Безопасность удалённого доступа", "other", "VPN, двухфакторность (по возможности), ограничения."),
    ("MEDPROT", "Защита медицинских изделий в сети", "medical", "Изоляция медконтура, согласование сканов."),
    ("TRAINING", "Обучение и инструктажи персонала", "other", "Инструктажи, журнал, повышение осведомлённости."),
    ("INCIDENT", "Реагирование на инциденты ИБ", "other", "Регламент, таймеры, evidence отправки, разбор."),
]

MAPPING = [
    ("117-ФЗ «О безопасности КИИ»", "ст. 7", ["KII-CAT"]),
    ("117-ФЗ «О безопасности КИИ»", "ст. 9", ["KII-SEC", "ASSET", "LOGGING"]),
    ("117-ФЗ «О безопасности КИИ»", "ст. 10", ["KII-SEC"]),
    ("152-ФЗ «О персональных данных»", "ст. 18.1", ["ASSET", "LOGGING"]),
    (
        "152-ФЗ «О персональных данных»",
        "ст. 19",
        ["PDN-ACC", "ACCESS", "ANTIVIR", "PATCH", "BACKUP"],
    ),
    ("152-ФЗ «О персональных данных»", "ст. 22.1", ["PDN-ACC"]),
    ("Приказы ФСТЭК России (СКЗИ)", "п. 5", ["SKZI-ACC"]),
    ("Приказы ФСТЭК России (СКЗИ)", "п. 6", ["SKZI-NET"]),
    ("Регламенты эксплуатации СКЗИ", "р. 1", ["SKZI-ACC", "KII-SEC"]),
]

# (код контроля, тип проверки, периодичность дней, обязательная, критерий, виды evidence)
TESTS = [
    ("KII-CAT", "document", 365, True, "перечень объектов КИИ утверждён, категории присвоены", ["document"]),
    ("KII-SEC", "interview", 365, False, "персонал знает меры СБ ЗО", ["screenshot"]),
    ("KII-SEC", "document", 365, False, "документы системы безопасности актуальны", ["document"]),
    ("ASSET", "scan", 30, True, "нет неизвестных активов сверх согласованного порога", ["export"]),
    ("ASSET", "document", 365, False, "реестр активов и ответственные актуальны", ["document"]),
    ("ACCESS", "config", 180, True, "учётные записи соответствуют приказу, пароли по политике", ["export", "screenshot"]),
    ("PDN-ACC", "config", 180, True, "доступ к ПДн — только по ролям и допускам", ["export"]),
    ("PDN-ACC", "interview", 365, False, "допуски подтверждены ответственными", ["screenshot"]),
    ("BACKUP", "restore", 30, True, "тестовое восстановление прошло успешно", ["act", "export"]),
    ("BACKUP", "config", 180, False, "расписание и глубина хранения по регламенту", ["screenshot"]),
    ("ANTIVIR", "config", 90, True, "все АРМ и серверы под защитой, базы актуальны", ["export"]),
    ("PATCH", "config", 90, True, "критические обновления установлены в срок", ["export"]),
    ("LOGGING", "config", 180, False, "журналы собираются, хранятся, доступ ограничен", ["screenshot"]),
    ("SKZI-ACC", "document", 365, True, "журналы учёта СКЗИ ведутся", ["document", "scan"]),
    ("SKZI-ACC", "config", 180, False, "условия эксплуатации СКЗИ соблюдаются", ["screenshot"]),
    ("SKZI-NET", "config", 365, True, "каналы с ПДн защищены СКЗИ", ["screenshot", "act"]),
    ("REMOTE", "config", 180, False, "удалённый доступ ограничен и журналируется", ["export"]),
    ("MEDPROT", "config", 180, False, "медконтур изолирован, сканы согласованы", ["screenshot"]),
    ("MEDPROT", "interview", 365, False, "владельцы медоборудования подтверждают режим", ["screenshot"]),
    ("TRAINING", "document", 365, True, "журнал инструктажей ведётся", ["document"]),
    ("INCIDENT", "document", 365, False, "регламент реагирования актуален", ["document"]),
    ("INCIDENT", "interview", 365, False, "дежурные знают порядок действий", ["screenshot"]),
]


def seed_catalog(apps, schema_editor) -> None:
    norm_act = apps.get_model("compliance", "NormAct")
    requirement = apps.get_model("compliance", "Requirement")
    control = apps.get_model("compliance", "Control")
    link = apps.get_model("compliance", "RequirementControlMap")
    control_test = apps.get_model("compliance", "ControlTest")

    for name, version in ACTS:
        norm_act.objects.get_or_create(name=name, defaults={"version": version})

    for act_name, clause, domain, text in REQUIREMENTS:
        act = norm_act.objects.get(name=act_name)
        requirement.objects.get_or_create(
            norm_act=act, clause=clause, defaults={"domain": domain, "text": text}
        )

    for code, name, domain, description in CONTROLS:
        control.objects.get_or_create(
            code=code, defaults={"name": name, "domain": domain, "description": description}
        )

    for act_name, clause, codes in MAPPING:
        req = requirement.objects.get(norm_act__name=act_name, clause=clause)
        for code in codes:
            link.objects.get_or_create(requirement=req, control=control.objects.get(code=code))

    for code, test_type, frequency, mandatory, criteria, kinds in TESTS:
        control_test.objects.get_or_create(
            control=control.objects.get(code=code),
            test_type=test_type,
            frequency_days=frequency,
            defaults={
                "is_mandatory": mandatory,
                "pass_criteria": criteria,
                "evidence_kinds": kinds,
            },
        )


def unseed_catalog(apps, schema_editor) -> None:
    codes = [code for code, *_ in CONTROLS]
    act_names = [name for name, _ in ACTS]
    apps.get_model("compliance", "ControlImplementation").objects.filter(
        control__code__in=codes
    ).delete()
    apps.get_model("compliance", "TestRun").objects.filter(
        test__control__code__in=codes
    ).delete()
    apps.get_model("compliance", "Control").objects.filter(code__in=codes).delete()
    apps.get_model("compliance", "NormAct").objects.filter(name__in=act_names).delete()


class Migration(migrations.Migration):
    dependencies = [("compliance", "0001_initial")]
    operations = [migrations.RunPython(seed_catalog, unseed_catalog)]
