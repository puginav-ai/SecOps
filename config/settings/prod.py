"""Прод (on-prem VM): hardening, работа за nginx с TLS.

Флаги ниже можно временно ослабить через окружение для dev-стенда (HTTP-доступ),
но по умолчанию — безопасные значения для сдачи.
"""

from config.env import env, env_bool, env_int

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")  # без default: в проде секрет обязателен

# Явное предупреждение в лог: открытый доступ — только для dev-стенда (SDD §4)
if REGISTRY_OPEN_ACCESS:  # noqa: F405
    import logging

    logging.getLogger("secops.security").warning(
        "REGISTRY_OPEN_ACCESS включён: консоль (включая запись) открыта без входа, "
        "анонимные запросы идут от имени OPEN_ACCESS_USER=%r. Недопустимо для сдачи — "
        "убрать из .env.",
        OPEN_ACCESS_USER,  # noqa: F405
    )

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", True)
