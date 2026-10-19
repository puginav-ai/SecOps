"""Уведомления: каналы in-app/SMTP, заглушки Telegram/мессенджера (SDD §3.6, неделя 6)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Факт отправки уведомления; dedup_key защищает от дублей при повторных прогонах задач."""

    class Channel(models.TextChoices):
        IN_APP = "in_app", "в приложении"
        EMAIL = "email", "почта"
        TELEGRAM = "telegram", "Telegram"
        MESSENGER = "messenger", "мессенджер"

    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="получатель (учётка)",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    recipient_email = models.EmailField("получатель (почта)", blank=True, default="")
    channel = models.CharField("канал", max_length=10, choices=Channel.choices)
    kind = models.CharField("вид", max_length=50)
    message = models.TextField("текст")
    instance = models.ForeignKey(
        "obligations.ObligationInstance",
        verbose_name="обязательство",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    incident = models.ForeignKey(
        "incidents.Incident",
        verbose_name="инцидент",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    dedup_key = models.CharField("ключ дедупликации", max_length=250, unique=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_channel_display()}: {self.kind}"
