"""Сервис уведомлений: in-app + SMTP; Telegram/мессенджер — заглушки до реквизитов
(Приложение В №4/№5)."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError

from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def validate_recipient(person) -> None:
    """Получатель обязан иметь учётку (in-app) или почту — валидация при назначении (SDD §3.5)."""
    if not person.user_id and not person.email:
        raise ValidationError(f"У «{person}» нет учётной записи и почты — уведомление невозможно")


def _send_email(email: str, kind: str, message: str) -> None:
    send_mail(
        subject=f"[Пульт ИБ] {kind}",
        message=message,
        from_email=None,
        recipient_list=[email],
        fail_silently=True,
    )


def _deliver(dedup_key: str, defaults: dict, *, email: str = "") -> int:
    """Создаёт уведомление; дубли (в т.ч. гонки beat) не считаются ошибкой."""
    try:
        _notification, created = Notification.objects.get_or_create(
            dedup_key=dedup_key, defaults=defaults
        )
    except IntegrityError:
        return 0
    if not created:
        return 0
    if email:
        _send_email(email, defaults["kind"], defaults["message"])
    return 1


def notify_user(
    user, kind: str, message: str, *, instance=None, incident=None, dedup_suffix: str = ""
) -> int:
    """Уведомление учётной записи: in-app + почта. Возвращает число новых отправок."""
    sent = 0
    base = (
        f"{kind}:{getattr(instance, 'pk', '-')}:inc{getattr(incident, 'pk', '-')}:"
        f"user{user.pk}:{dedup_suffix}"
    )
    sent += _deliver(
        f"{base}:in_app",
        {
            "recipient_user": user,
            "channel": Notification.Channel.IN_APP,
            "kind": kind,
            "message": message,
            "instance": instance,
            "incident": incident,
        },
    )
    if user.email:
        sent += _deliver(
            f"{base}:email",
            {
                "recipient_email": user.email,
                "channel": Notification.Channel.EMAIL,
                "kind": kind,
                "message": message,
                "instance": instance,
                "incident": incident,
            },
            email=user.email,
        )
    return sent


def notify_person(
    person, kind: str, message: str, *, instance=None, incident=None, dedup_suffix: str = ""
) -> int:
    """Уведомление человека из реестра: in-app через его учётку и/или на почту."""
    sent = 0
    base = (
        f"{kind}:{getattr(instance, 'pk', '-')}:inc{getattr(incident, 'pk', '-')}:"
        f"person{person.pk}:{dedup_suffix}"
    )
    if person.user_id:
        sent += _deliver(
            f"{base}:in_app",
            {
                "recipient_user": person.user,
                "channel": Notification.Channel.IN_APP,
                "kind": kind,
                "message": message,
                "instance": instance,
                "incident": incident,
            },
        )
    if person.email:
        sent += _deliver(
            f"{base}:email",
            {
                "recipient_email": person.email,
                "channel": Notification.Channel.EMAIL,
                "kind": kind,
                "message": message,
                "instance": instance,
                "incident": incident,
            },
            email=person.email,
        )
    if not person.user_id and not person.email:
        logger.warning("recipient has no channels", extra={"person_id": person.pk})
    # Telegram/мессенджер: адаптеры каркасом — до получения реквизитов (Приложение В №4/№5)
    return sent
