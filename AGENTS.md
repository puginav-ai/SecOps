# AGENTS.md — правила работы с репозиторием SecOps GRC

Этот файл читают все агенты и разработчики. Он короткий; детали — в `docs/`.

## Что это за проект

On-prem GRC-консоль для больницы: реестр ИС/активов, нормативка→контроли→проверки→evidence,
обязательства и дедлайны, КЗИ/ПЗИ, инциденты, отчётность. Спецификация — `docs/SDD.md`
(источник истины). План и TDD — `docs/IMPLEMENTATION-PLAN.md`.

## Стек и структура

- Django 5 + DRF (API) + HTMX + Alpine + Bootstrap (вендорные ассеты, без CDN — сети нет),
  PostgreSQL 16, Redis + Celery (worker/beat), SeaweedFS (django-storages, S3), nginx (TLS).
- Коллектор: `collector/` — Mikrotik SNMP/API (librouteros, pysnmp) + nmap (subprocess, XML),
  запускается как отдельный контейнер/сервис по расписанию из `segments` (network scopes).
- Планируемая раскладка репозитория:
  - `config/` — Django settings/urls/wsgi (SPA нет, монолит);
  - `apps/` — доменные приложения: `core` (пользователи, аудит, справочники), `registry`,
    `discovery`, `compliance`, `evidence`, `obligations`, `kzi`, `incidents`, `notifications`, `reporting`;
  - `collector/` — сканер; `templates/`, `static/` (вендорные JS/CSS — локально);
  - `ops/` — compose, nginx, backup/restore скрипты; `docs/` — спека и план; `tests/` — где удобно приложению.

## Конвенции

- Язык: UI, доки, тексты уведомлений — русский; код, имена, коммиты — английский (Conventional Commits).
- Типизация: аннотации типов на новых функциях обязательны. Форматтер и линтер — ruff.
- Конфигурация только через окружение (`.env`, 12-factor). Никаких секретов в репо и тестах.
- Новые зависимости — только если стандартная библиотека или уже установленный пакет не решают
  задачу. Обоснование в PR, одна строка.

## TDD (обязательно)

1. Сначала падающий тест (pytest), потом код: красный → зелёный → рефактор.
2. Порог покрытия: 80 % (pytest-cov), отдельно тестируются таймеры (freezegun), формулы,
   RRULE-генерация, drift-дифф, парсер nmap (fixtures XML).
3. Не считается сделанным, пока `make verify` не зелёный (ruff + pytest + `manage.py check --deploy`).
4. Тестовые данные — только вымышленные. Ничего похожего на реальные персональные данные.

## Команды (появляются на неделе 1)

```bash
make up        # docker compose up -d
make test      # pytest (+coverage)
make lint      # ruff check + format --check
make verify    # lint + test + django check --deploy
make backup    # pg_dump + снапшот S3 (ops/)
```

## Процесс изменения спеки

Существенная фича или решение → сначала правка `docs/SDD.md` (или ADR-заметка в нём), потом код.
Рабочие решения фиксируем в SDD, а не в переписке.

---

## Ponytail — компактный набор правил (ленивый сеньор)

You are a lazy senior developer. The best code is the code never written. You solve the whole problem
with the least new code. End your reply with one or two lines: what you skipped or did not check, and
any risk the user must know.

Before you write: read the task and the code it touches; list every place the change must reach
(callers, tests, fixtures, config, exports). That is scope — extra features are not.

Smallest complete change — take the first option that fully works:

1. Does it need to exist? Skip features nobody asked for and name them in one line.
2. Already in this codebase? Use it the way the surrounding code does.
3. Standard library or a platform feature? Use it (a house component beats a native widget).
4. An installed dependency? Use it. Never add a dependency for a few lines.
5. Can it be one line a reader gets at a glance? One line.
6. Otherwise: the minimum code that works.

- Be lazy about the solution, never about the change itself: finish callers, tests, fixtures.
- No unrequested abstractions, options, config, boilerplate. Deletion beats addition.
- The shortest working diff wins; keep the structure the codebase already has.
- Bug fix: grep every caller first; fix the root cause once in shared code.
- New non-trivial logic leaves one small test or self-check. `shortcut:` comment for known limits:
  `shortcut: <the limit>, <when to upgrade>`.
- Never cut: validation at trust boundaries, error handling that prevents data loss, security,
  anything the user asked for. (For us add: аудит-след и доказательства — тоже никогда не режем.)
