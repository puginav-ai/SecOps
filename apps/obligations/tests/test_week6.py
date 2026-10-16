"""Неделя 6: материализация RRULE, напоминания 30/7/1, эскалации, закрытие с evidence."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from freezegun import freeze_time

from apps.evidence.models import EvidenceObject
from apps.notifications.models import Notification
from apps.obligations import services
from apps.obligations.models import ObligationInstance, ObligationTemplate
from apps.obligations.tasks import daily_obligations
from apps.registry.models import Person

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner() -> Person:
    return Person.objects.create(fio="Владелец Обязательств", email="owner@example.test")


def make_template(**overrides) -> ObligationTemplate:
    defaults = {
        "kind": ObligationTemplate.Kind.KZI,
        "name": "Оценка КЗИ",
        "recurrence_rule": "FREQ=MONTHLY;INTERVAL=6",
    }
    defaults.update(overrides)
    return ObligationTemplate.objects.create(**defaults)


@freeze_time("2026-10-19 09:00:00+05:00")
def test_materialize_generates_horizon_and_is_idempotent() -> None:
    template = make_template()
    now = timezone.now()

    created = services.materialize(template, now)
    again = services.materialize(template, now)

    assert created == 4  # 0, +6, +12, +18 месяцев
    assert again == 0
    assert template.instances.count() == 4


@freeze_time("2026-10-19 09:00:00+05:00")
def test_one_off_template_single_instance() -> None:
    template = make_template(recurrence_rule="")

    assert services.materialize(template, timezone.now()) == 1
    assert services.materialize(template, timezone.now()) == 0


@freeze_time("2026-10-19 09:00:00+05:00")
def test_reminder_on_cadence_once(owner: Person, mailoutbox) -> None:
    template = make_template(name="Отчёт", recurrence_rule="", lead_days=[30, 7, 1])
    ObligationInstance.objects.create(
        template=template, due_at=timezone.now() + timedelta(days=30), owner_person=owner
    )

    sent = services.send_reminders(timezone.now())
    again = services.send_reminders(timezone.now())

    assert sent == 1  # у владельца есть только почта
    assert again == 0
    assert len(mailoutbox) == 1


@freeze_time("2026-10-19 09:00:00+05:00")
def test_no_reminder_off_cadence(owner: Person) -> None:
    template = make_template(recurrence_rule="", lead_days=[30])
    ObligationInstance.objects.create(
        template=template, due_at=timezone.now() + timedelta(days=29), owner_person=owner
    )

    assert services.send_reminders(timezone.now()) == 0


@freeze_time("2026-10-19 09:00:00+05:00")
def test_escalation_after_overdue_once(make_user, owner: Person) -> None:
    make_user("admin-esc", role="ib_admin")
    template = make_template(
        name="Бэкапы",
        recurrence_rule="",
        escalation_policy=[{"step": 1, "after_days": 3, "recipients": [{"role": "ib_admin"}]}],
    )
    instance = ObligationInstance.objects.create(
        template=template,
        due_at=timezone.now() - timedelta(days=5),
        status=ObligationInstance.Status.OVERDUE,
        owner_person=owner,
    )

    sent = services.run_escalations(timezone.now())
    again = services.run_escalations(timezone.now())
    instance.refresh_from_db()

    assert sent >= 1
    assert again == 0
    assert instance.escalation_level == 1
    assert Notification.objects.filter(kind="obligation_escalation").exists()


@freeze_time("2026-10-19 09:00:00+05:00")
def test_daily_run_refreshes_statuses(owner: Person) -> None:
    template = make_template(recurrence_rule="")
    instance = ObligationInstance.objects.create(
        template=template, due_at=timezone.now() + timedelta(days=10), owner_person=owner
    )

    result = daily_obligations()  # в тестах celery eager

    instance.refresh_from_db()
    assert instance.status == ObligationInstance.Status.DUE_SOON
    assert result["created"] >= 1  # периодические шаблоны из сида материализуются
    assert result["statuses"] >= 1


def test_close_requires_evidence_when_template_requires(
    client, login, make_user, owner: Person
) -> None:
    template = make_template(name="КЗИ", recurrence_rule="", requires_closing_evidence=True)
    instance = ObligationInstance.objects.create(
        template=template, due_at=timezone.now(), owner_person=owner
    )
    client = login(make_user("officer-ob", role="ib_officer"))

    response = client.post(f"/obligations/{instance.pk}/close/", {"evidence": ""})
    assert response.status_code == 200
    instance.refresh_from_db()
    assert instance.status == ObligationInstance.Status.PLANNED

    evidence = EvidenceObject.objects.create(
        title="Протокол КЗИ", file=SimpleUploadedFile("kzi.pdf", b"x")
    )
    response = client.post(f"/obligations/{instance.pk}/close/", {"evidence": evidence.pk})
    assert response.status_code == 302
    instance.refresh_from_db()
    assert instance.status == ObligationInstance.Status.DONE
    assert instance.closure_evidence_id == evidence.pk


def test_obligation_list_shows_overdue(client, login, make_user, owner: Person) -> None:
    template = make_template(name="Просроченное дело", recurrence_rule="")
    ObligationInstance.objects.create(
        template=template,
        due_at=timezone.now() - timedelta(days=1),
        status=ObligationInstance.Status.OVERDUE,
        owner_person=owner,
    )
    client = login(make_user("officer-list", role="ib_officer"))

    body = client.get("/obligations/").content.decode()

    assert "Просроченное дело" in body


def test_my_notifications_view(client, login, make_user) -> None:
    user = make_user("owner-ui", role="ib_officer")
    Notification.objects.create(
        recipient_user=user,
        channel=Notification.Channel.IN_APP,
        kind="test",
        message="Привет из уведомлений",
        dedup_key="test-1",
    )
    client = login(user)

    body = client.get("/notifications/").content.decode()

    assert "Привет из уведомлений" in body
