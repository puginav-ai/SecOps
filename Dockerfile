# Единый образ для web/worker/beat (и прогонов pytest). On-prem, без swarm/k8s.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# nmap нужен контейнеру collector (профиль scan): sweep/порт-скан; iputils-ping — для
# индикатора Ping в паспорте актива. В web/worker лежит в том же образе — осознанно,
# ради единого образа (см. SDD §2.2).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nmap iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
# dev-зависимости в образе осознанно: на VM нет venv, `make test` идёт в этом же образе
# (shortcut: при росте образа — вынести в отдельный target)
RUN pip install --no-cache-dir -r requirements-dev.txt

RUN useradd --uid 1000 --create-home app
COPY --chown=app:app . .
RUN mkdir -p /app/staticfiles && chown app:app /app/staticfiles \
    && chmod +x /app/ops/entrypoint.sh

USER app
EXPOSE 8000

ENTRYPOINT ["/app/ops/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
