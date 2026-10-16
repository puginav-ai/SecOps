"""Страховочный аудит мутаций (SDD §3.8).

Сервисный слой модулей пишет обогащённые записи (entity_type/entity_id/diff);
мидлварь фиксирует базовый факт мутации, чтобы ни одна операция не осталась без следа.
Входы/выходы — в логе приложения, не в audit_log (SDD §8).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.models import AuditLog

logger = logging.getLogger(__name__)

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
