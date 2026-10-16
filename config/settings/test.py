"""Настройки для pytest: быстрые хэши, locmem-почта, eager-задачи. Только вымышленные данные."""

from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Тесты не зависят от локального .env: dev-режим реестра управляется только фикстурой settings
REGISTRY_OPEN_ACCESS = False
# Дополнительные источники пассивных данных включаются только в тестах, где они нужны
MIKROTIK_EXTRA_ROUTERS = []
