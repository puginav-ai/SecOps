# Браузерный e2e-прогон (Playwright/Chromium): `make e2e` (неделя 12).
# Отдельный образ намеренно НЕ зависит от образа приложения: смоук-скрипт ходит по HTTP
# к живому стенду, Django ему не нужен — пересборка приложения Chromium не переустанавливает.
FROM python:3.12-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir 'playwright>=1.40,<2' \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ops/e2e/browser_smoke.py /app/browser_smoke.py
