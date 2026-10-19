"""Браузерный e2e-дым (Playwright/Chromium): логин и обход ключевых разделов живой консоли.

Запуск: `make e2e` — образ secops-e2e поверх web, стек доступен как https://nginx
(внутри compose-сети, самоподписанный сертификат). Учётные данные — только из окружения
(.env: E2E_USER/E2E_PASSWORD): секретов в репозитории нет.

Проверяет: все разделы отвечают 200, нет JS-исключений и незагруженных same-origin ресурсов
(вендорные JS/CSS), нет страниц с «Server Error». Прогон только читающий — данные не меняет.
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "https://nginx").rstrip("/")
USER = os.environ.get("E2E_USER", "grc-admin")
PASSWORD = os.environ.get("E2E_PASSWORD", "")

PAGES: list[tuple[str, str]] = [
    ("/", "дашборд"),
    ("/registry/", "реестр"),
    ("/registry/assets/unknown/", "unknown assets"),
    ("/registry/map/", "карта сети"),
    ("/compliance/", "матрица контролей"),
    ("/evidence/", "evidence"),
    ("/obligations/", "обязательства"),
    ("/notifications/", "уведомления"),
    ("/incidents/", "инциденты"),
    ("/kzi/", "КЗИ"),
    ("/reports/", "отчёты"),
    ("/reports/management/", "отчёт руководству"),
]


def main() -> int:
    if not PASSWORD:
        print("E2E_PASSWORD не задан: секреты в репозитории не храним.")
        print("Задайте E2E_USER/E2E_PASSWORD в .env.")
        return 2

    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page_errors: list[str] = []
        failed_requests: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        def note_failure(request) -> None:
            if request.url.startswith(BASE_URL) and "favicon" not in request.url:
                failed_requests.append(f"{request.method} {request.url}: {request.failure}")

        page.on("requestfailed", note_failure)

        page.goto(f"{BASE_URL}/accounts/login/", wait_until="domcontentloaded")
        page.fill('input[name="username"]', USER)
        page.fill('input[name="password"]', PASSWORD)
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        if "/accounts/login" in page.url:
            failures.append("логин не прошёл: остались на странице входа")

        for path, title in PAGES:
            errors_before, requests_before = len(page_errors), len(failed_requests)
            response = page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
            status = response.status if response else None
            if status != 200:
                failures.append(f"{path} ({title}): HTTP {status}")
                continue
            content = page.content()
            if "Server Error" in content or "Traceback" in content:
                failures.append(f"{path} ({title}): страница ошибки")
            for error in page_errors[errors_before:]:
                failures.append(f"{path} ({title}): JS-исключение: {error}")
            for request in failed_requests[requests_before:]:
                failures.append(f"{path} ({title}): ресурс не загрузился — {request}")

        context.close()
        browser.close()

    if failures:
        print("E2E: ПРОВАЛ")
        for failure in failures:
            print(" -", failure)
        return 1
    print(f"E2E_OK: вход выполнен, разделов проверено — {len(PAGES)}, ошибок нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
