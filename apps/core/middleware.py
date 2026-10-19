"""Страховочный аудит мутаций (SDD §3.8).

Сервисный слой модулей пишет обогащённые записи (entity_type/entity_id/diff);
мидлварь фиксирует базовый факт мутации, чтобы ни одна операция не осталась без следа.
Входы/выходы — в логе приложения, не в audit_log (SDD §8).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse

from apps.core.models import AuditLog

logger = logging.getLogger(__name__)

_open_access_warn_emitted = False

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
EXEMPT_PREFIXES = ("/accounts/login/", "/accounts/logout/")


def client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditLogMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        self._log(request, response)
        return response

    def _log(self, request: HttpRequest, response: HttpResponse) -> None:
        try:
            if request.method in SAFE_METHODS:
                return
            if request.path.startswith(EXEMPT_PREFIXES):
                return
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return
            if response.status_code >= 400:
                return
            match = getattr(request, "resolver_match", None)
            view_name = getattr(match, "view_name", None) if match else None
            action = view_name or f"{request.method} {request.path}"
            AuditLog.write(action=action, actor=user, actor_ip=client_ip(request))
        except Exception:
            # Ответ уже отдан; сбой аудита не ломает его, но обязан быть громким.
            # shortcut: запись вне транзакции мутации — при переносе логики в сервисный слой
            # писать аудит в той же транзакции, что и мутацию.
            logger.exception("audit_log: не удалось записать событие", extra={"path": request.path})


class OpenAccessMiddleware:
    """Dev-режим «без входа»: анонимные запросы выполняются от имени OPEN_ACCESS_USER (ADR §4).

    Пока `REGISTRY_OPEN_ACCESS=1`, логин не требуется: дашборд, отчёты и запись доступны
    анонимно, а мутации попадают в `audit_log` от имени настроенного пользователя (у режима
    «только реестр» актор оставался пустым). Если пользователь не найден — предупреждаем в
    лог и работает только историческое поведение (открытый реестр). Перед сдачей выключить:
    консоль целиком без авторизации — недопустимо для эксплуатации.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        global _open_access_warn_emitted
        if settings.REGISTRY_OPEN_ACCESS and not request.user.is_authenticated:
            user = None
            if settings.OPEN_ACCESS_USER:
                user = (
                    get_user_model()
                    .objects.filter(username=settings.OPEN_ACCESS_USER, is_active=True)
                    .first()
                )
            if user is not None:
                request.user = user
            elif not _open_access_warn_emitted:
                _open_access_warn_emitted = True
                logger.warning(
                    "OPEN_ACCESS_USER=%r не найден: открытый доступ действует только для реестра.",
                    settings.OPEN_ACCESS_USER,
                )
        return self.get_response(request)
