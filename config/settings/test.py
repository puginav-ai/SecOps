"""Настройки для pytest: быстрые хэши, locmem-почта, eager-задачи. Только вымышленные данные."""

import tempfile
from pathlib import Path

from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Тесты не зависят от локального .env: dev-режим реестра управляется только фикстурой settings
REGISTRY_OPEN_ACCESS = False
OPEN_ACCESS_USER = ""
# Дополнительные источники пассивных данных включаются только в тестах, где они нужны
MIKROTIK_EXTRA_ROUTERS = []

# Evidence: локальное хранилище во временном каталоге — тесты не зависят от .env и S3
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="secops-evidence-"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
