"""Локальная разработка: DEBUG, свободные хосты, почта в консоль."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "*")  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
