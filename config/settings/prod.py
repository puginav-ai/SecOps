"""Прод (on-prem VM): hardening, работа за nginx с TLS."""

from config.env import env

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")  # без default: в проде секрет обязателен

# Явное предупреждение в лог: открытый реестр — только для dev-стенда (SDD §4)
if REGISTRY_OPEN_ACCESS:  # noqa: F405
    import logging

    logging.getLogger("secops.security").warning(
        "REGISTRY_OPEN_ACCESS включён: реестр открыт анонимно. "
        "Недопустимо для сдачи — убрать из .env."
    )

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
