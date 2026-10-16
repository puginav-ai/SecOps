"""Контракт настроек безопасности (SDD §8; значения — уточняются Приложением В №9)."""

from __future__ import annotations

from django.conf import settings


def test_password_min_length_is_12():
    validators = {item["NAME"]: item for item in settings.AUTH_PASSWORD_VALIDATORS}
    minimum = validators["django.contrib.auth.password_validation.MinimumLengthValidator"]
    assert minimum["OPTIONS"]["min_length"] == 12


def test_session_cookie_age_default_8h():
    assert settings.SESSION_COOKIE_AGE == 8 * 3600


def test_argon2_is_primary_password_hasher_in_base_settings():
    # Проверяем базовый модуль настроек: тестовые сознательно переопределяют хэшер на быстрый MD5.
    from config.settings import base as base_settings

    assert base_settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")


def test_audit_middleware_is_wired_last():
    assert settings.MIDDLEWARE[-1] == "apps.core.middleware.AuditLogMiddleware"
