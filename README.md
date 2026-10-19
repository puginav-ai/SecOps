# SecOps GRC — пульт управления информационной безопасностью

On-prem GRC-консоль для больницы: реестр ИС/активов, нормативка → контроли → проверки →
evidence, обязательства с дедлайнами, КЗИ/ПЗИ, инциденты, отчётность.

- Спецификация (источник истины): [docs/SDD.md](docs/SDD.md)
- Процесс и план (TDD, 12 недель): [docs/IMPLEMENTATION-PLAN.md](docs/IMPLEMENTATION-PLAN.md)
- Регламент (evidence, проверки, RACI, обучение): [docs/REGULATIONS.md](docs/REGULATIONS.md)
- Правила разработки: [AGENTS.md](AGENTS.md)

## Быстрый старт

Требуется Docker с Compose. Всё выполняется в контейнерах (на VM нет venv).

```bash
cp .env.example .env        # заполнить секреты: openssl rand -hex 32
sh ops/certs/gen-dev-cert.sh   # dev-сертификат (прод — внутренний УЦ)
make up                     # соберёт образ и поднимет стек
make superuser              # первый пользователь (is_staff + is_superuser)
```

UI: https://localhost (dev-сертификат самоподписанный — предупреждение браузера ожидаемо).
Если порты 80/443 заняты другой службой: `HTTP_PORT=8080 HTTPS_PORT=8443 make up` —
UI на https://localhost:8443.
Роли выдаются в админке `/admin/` (группы `ib_admin`, `ib_officer`, `it_ops`,
`system_owner`, `reader` создаются миграцией).

## Команды

| Команда | Что делает |
|---|---|
| `make up` / `make down` | поднять/остановить стек |
| `make scan-up` | поднять коллектор discovery (профиль `scan`, нужен `NET_RAW`) |
| `make test` | pytest + покрытие (порог 80 %) |
| `make lint` / `make fix` | ruff check/format (--check / с автоправкой) |
| `make verify` | lint + test + `manage.py check --deploy` — критерий «сделано» |
| `make migrate` / `make makemigrations` | миграции |
| `make backup` / `make restore-check` | бэкап и проверка восстановления (см. `ops/`) |
| `make audit-list` | список адресов для скана (ARP всех роутеров-источников) → `machines.txt` |
| `make e2e` | браузерный e2e (Playwright/Chromium) по живой консоли; логин — `E2E_USER`/`E2E_PASSWORD` в `.env` |

## Конвенции

- Код, имена, коммиты — английский (Conventional Commits); UI/доки/уведомления — русский.
- Конфигурация — только через окружение (`.env`, в репозиторий не попадает).
- Разработка — строго по TDD: сначала падающий тест (см. AGENTS.md).
