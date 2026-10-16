"""Базовые настройки: общие для dev/test/prod. Конфигурация — только через окружение (12-factor)."""

from __future__ import annotations

from decimal import Decimal

from celery.schedules import crontab

from config.env import BASE_DIR, env, env_int, env_json, env_list, load_dotenv

load_dotenv()

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.registry",
    "apps.discovery",
    "apps.compliance",
    "apps.evidence",
    "apps.obligations",
    "apps.notifications",
    "apps.kzi",
    "apps.reporting",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "secops"),
        "USER": env("POSTGRES_USER", "secops"),
        "PASSWORD": env("POSTGRES_PASSWORD", "secops"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
    }
}

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Yekaterinburg"  # часовой пояс больницы (роутеры настроены на UTC+5)
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Файловое хранилище evidence (неделя 5): по умолчанию локальное, в проде — S3 (SeaweedFS).
MEDIA_ROOT = BASE_DIR / "media"
EVIDENCE_STORAGE_BACKEND = (
    env("EVIDENCE_STORAGE", "") or "django.core.files.storage.FileSystemStorage"
)
STORAGES = {
    "default": {"BACKEND": EVIDENCE_STORAGE_BACKEND},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
AWS_ACCESS_KEY_ID = env("S3_ACCESS_KEY", "")
AWS_SECRET_ACCESS_KEY = env("S3_SECRET_KEY", "")
AWS_STORAGE_BUCKET_NAME = env("S3_BUCKET", "evidence")
AWS_S3_ENDPOINT_URL = env("S3_ENDPOINT", "")
AWS_S3_REGION_NAME = env("S3_REGION", "us-east-1")
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True

# Ограничения загрузки evidence (SDD §5.4)
EVIDENCE_MAX_MB = env_int("EVIDENCE_MAX_MB", 100)
EVIDENCE_ALLOWED_EXTENSIONS = env_list(
    "EVIDENCE_ALLOWED_EXTENSIONS",
    "pdf,doc,docx,odt,rtf,txt,csv,xlsx,ods,xml,json,png,jpg,jpeg,zip,rar,7z,cfg,log",
)

# Пороги вердикта КЗИ (SDD §3.4; уточняются по Приложению В №10)
KZI_VERDICT_HIGH = Decimal(env("KZI_VERDICT_HIGH", "0.95"))
KZI_VERDICT_MEDIUM = Decimal(env("KZI_VERDICT_MEDIUM", "0.80"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 8 * 3600)  # default 8 ч (Приложение В, №9)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# Временный dev-режим: реестр открыт без входа (ADR §4). В prod не включать.
REGISTRY_OPEN_ACCESS = env("REGISTRY_OPEN_ACCESS", "0") != "0"

# Почта: SMTP подключается реквизитами (неделя 6). До этого — console-бэкенд.
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "1") != "0"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "secops@localhost")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)

# Пассивное обнаружение через RouterOS API (Приложение В №2): MIKROTIK_HOST пуст → выключено.
MIKROTIK_HOST = env("MIKROTIK_HOST", "")
MIKROTIK_API_USER = env("MIKROTIK_API_USER", "admin")
MIKROTIK_API_PASSWORD = env("MIKROTIK_API_PASSWORD", "")
MIKROTIK_API_SSL = env("MIKROTIK_API_SSL", "0") != "0"
# Дополнительные источники пассивных данных (в т.ч. «маленькие» роутеры):
# JSON-список [{"host": "10.0.2.2", "user": "secops", "password": "..."}]. Пусто → только основной.
MIKROTIK_EXTRA_ROUTERS = env_json("MIKROTIK_EXTRA_ROUTERS", [])

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
# Сканы идут в отдельную очередь: её слушает контейнер collector (профиль scan, NET_RAW).
CELERY_TASK_ROUTES = {"apps.discovery.tasks.scan_segment": {"queue": "scan"}}
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "scan-due-segments": {
        "task": "apps.discovery.tasks.scan_due_segments",
        "schedule": crontab(minute="*/30"),
    },
    # Утро буднего дня: материализация обязательств, статусы, напоминания 30/7/1, эскалации
    "obligations-daily": {
        "task": "apps.obligations.tasks.daily_obligations",
        "schedule": crontab(hour=8, minute=5),
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "config.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"level": "WARNING", "propagate": True},
        "django.security": {"level": "WARNING", "propagate": True},
    },
}
