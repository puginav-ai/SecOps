# SecOps GRC — базовые команды. Всё выполняется в Docker (на VM нет venv).
COMPOSE := docker compose -f ops/compose.yaml
RUN := $(COMPOSE) run --rm
MOUNT := -v $(CURDIR):/app

.PHONY: help up down build logs test lint fix verify check-deploy migrate makemigrations superuser shell backup restore-check scan-up

help:
	@grep -E '^[a-zA-Z_-]+:' Makefile | cut -d: -f1 | sort

up:
	$(COMPOSE) up -d --build

scan-up:
	$(COMPOSE) --profile scan up -d collector

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f --tail=100

test:
	$(RUN) -e DJANGO_SETTINGS_MODULE=config.settings.test $(MOUNT) web python -m pytest

lint:
	$(RUN) --no-deps $(MOUNT) web ruff check .
	$(RUN) --no-deps $(MOUNT) web ruff format --check .

fix:
	$(RUN) --no-deps $(MOUNT) web ruff check --fix .
	$(RUN) --no-deps $(MOUNT) web ruff format .

verify: lint test check-deploy

check-deploy:
	$(RUN) -e DJANGO_SETTINGS_MODULE=config.settings.prod -e DJANGO_SECRET_KEY=check-only-0123456789abcdef0123456789abcdef0123456789abcdef $(MOUNT) web python manage.py check --deploy

migrate:
	$(RUN) -e DJANGO_SETTINGS_MODULE=config.settings.prod -e DJANGO_SECRET_KEY=check-only-0123456789abcdef0123456789abcdef0123456789abcdef $(MOUNT) web python manage.py migrate

makemigrations:
	$(RUN) --no-deps -e DJANGO_SETTINGS_MODULE=config.settings.dev $(MOUNT) web python manage.py makemigrations

superuser:
	$(RUN) $(MOUNT) web python manage.py createsuperuser

shell:
	$(RUN) $(MOUNT) web python manage.py shell

backup:
	ops/backup.sh

restore-check:
	ops/restore-check.sh
