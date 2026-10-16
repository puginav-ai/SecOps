"""Доменные модели ядра: пользователь и журнал аудита."""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Пользователь системы. Роли — Django groups (RBAC, SDD §4)."""

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


class AuditLog(models.Model):
    """Аудит мутаций. Append-only: изменять/удалять через приложение нельзя (SDD §3.8)."""

    at = models.DateTimeField("время", auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        User,
        verbose_name="кто",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_entries",
    )
    actor_ip = models.GenericIPAddressField("IP", null=True, blank=True)
    action = models.CharField("действие", max_length=200)
    entity_type = models.CharField("тип сущности", max_length=100, blank=True, default="")
    entity_id = models.CharField("id сущности", max_length=64, blank=True, default="")
    diff = models.JSONField("изменения", null=True, blank=True)

    class Meta:
        verbose_name = "Запись аудита"
        verbose_name_plural = "Журнал аудита"
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M:%S} {self.actor_id or '—'} {self.action}"

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            raise RuntimeError("audit_log append-only: изменение записей запрещено")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        raise RuntimeError("audit_log append-only: удаление записей запрещено")

    @classmethod
    def write(
        cls,
        *,
        action: str,
        actor=None,
        actor_ip: str | None = None,
        entity_type: str = "",
        entity_id: str = "",
        diff: dict | None = None,
    ) -> AuditLog:
        return cls.objects.create(
            action=action,
            actor=actor,
            actor_ip=actor_ip,
            entity_type=entity_type,
            entity_id=entity_id,
            diff=diff,
        )
