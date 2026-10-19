# Браузерный e2e-прогон (Playwright/Chromium) поверх web-образа: `make e2e` (неделя 12).
# Отдельный образ — apt-зависимости Chromium и сам браузер (~400 МБ) в прод-образ web не попадают.
FROM secops-web:latest

USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir 'playwright>=1.40,<2' \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*
USER app
