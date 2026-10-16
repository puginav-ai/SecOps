"""RBAC (SDD §4): матрица «роль × модуль» и декоратор role_required.

Значения: "rw" — чтение и запись, "r" — только чтение, "" — нет доступа.
Для system_owner в SDD ячейки «свои ИС»: здесь базовый доступ к модулю, точная видимость
объектов — фильтрами queryset в модулях (systems.owner_person_id).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

MODULES: dict[str, str] = {
    "registry": "Реестр ИС/активов",
    "discovery": "Discovery",
    "compliance": "Контроли и проверки",
    "evidence": "Evidence",
    "obligations": "Обязательства",
    "kzi": "КЗИ/ПЗИ",
    "incidents": "Инциденты",
    "reports": "Отчёты",
    "admin": "Администрирование",
}

ROLE_TITLES: dict[str, str] = {
    "ib_admin": "ИБ-админ",
    "ib_officer": "ИБ",
    "it_ops": "ИТ",
    "system_owner": "Владелец ИС",
    "reader": "Руководство",
}

ROLE_MATRIX: dict[str, dict[str, str]] = {
    "ib_admin": dict.fromkeys(MODULES, "rw"),
    "ib_officer": {**dict.fromkeys(MODULES, "rw"), "admin": ""},
    "it_ops": {
        "registry": "rw",
        "discovery": "rw",
        "compliance": "r",
        "evidence": "r",
        "obligations": "r",
        "kzi": "",
        "incidents": "r",
        "reports": "r",
        "admin": "",
    },
    "system_owner": {
        "registry": "rw",
        "discovery": "r",
        "compliance": "rw",
        "evidence": "rw",
        "obligations": "rw",
        "kzi": "r",
        "incidents": "rw",
        "reports": "rw",
        "admin": "",
    },
    "reader": {
        "registry": "r",
        "discovery": "",
        "compliance": "r",
        "evidence": "r",
        "obligations": "r",
        "kzi": "r",
        "incidents": "r",
        "reports": "r",
        "admin": "",
    },
}


def user_roles(user) -> set[str]:
    """Коды ролей (групп) пользователя."""
    if not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True))


# Роли, которым виден весь реестр (без фильтра «только свои ИС», SDD §4)
FULL_REGISTRY_ROLES = {"ib_admin", "ib_officer", "it_ops", "reader"}


def is_owner_only(user) -> bool:
    """True, если пользователь — только владелец ИС (видит лишь свои системы, SDD §4)."""
    roles = user_roles(user)
    return "system_owner" in roles and not roles & FULL_REGISTRY_ROLES


def module_access(user, module: str) -> str:
    """Итоговый доступ к модулю: максимум по ролям; суперпользователь — «rw» везде."""
    if not user.is_authenticated:
        # временный dev-режим: реестр открыт без входа (ADR §4), остальные модули — нет
        if module == "registry" and settings.REGISTRY_OPEN_ACCESS:
            return "rw"
        return ""
    if user.is_superuser:
        return "rw"
    best = ""
    for role in user_roles(user):
        access = ROLE_MATRIX.get(role, {}).get(module, "")
        if access == "rw":
            return "rw"
        if access == "r":
            best = "r"
    return best


def user_modules(user) -> list[tuple[str, str]]:
    """Видимые пользователю модули: [(код, доступ)]."""
    return [(code, access) for code in MODULES if (access := module_access(user, code))]


def role_required(module: str, level: str = "r") -> Callable:
    """Пускает во view, если доступ к модулю не ниже level ("r" | "rw").

    Анонимные пользователи перенаправляются на логин, авторизованные без доступа —
    403 (PermissionDenied). Исключение: временный dev-режим REGISTRY_OPEN_ACCESS
    открывает модуль registry анонимам (ADR §4); для вошедших матрица ролей не меняется.
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if module == "registry" and settings.REGISTRY_OPEN_ACCESS:
                    return view_func(request, *args, **kwargs)
                return redirect_to_login(request.get_full_path())
            access = module_access(request.user, module)
            if not (access == "rw" or (level == "r" and access == "r")):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
