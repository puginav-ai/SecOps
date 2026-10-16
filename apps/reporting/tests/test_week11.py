"""Неделя 11: отчёты — доступ, состав, выгрузки."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_reports_requires_login(client) -> None:
    response = client.get("/reports/")

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_reports_shows_sections(client, login, make_user) -> None:
    client = login(make_user("officer-rep", role="ib_officer"))

    body = client.get("/reports/").content.decode()

    assert "Состояние контролей" in body
    assert "Просроченные обязательства" in body
    assert "Покрытие evidence по видам" in body
    assert "Оценки КЗИ/ПЗИ" in body


def test_gaps_csv_headers_and_access(client, login, make_user) -> None:
    client = login(make_user("officer-csv", role="ib_officer"))

    response = client.get("/reports/gaps.csv")

    assert response.status_code == 200
    body = response.content.decode("utf-8-sig")
    assert body.startswith("Код;Контроль;Домен;ИС;Статус;Ответственный;Следующая проверка")


def test_reader_can_view_reports_and_export(client, login, make_user) -> None:
    """«Руководство» читает отчёты (в матрице ролей — только чтение)."""
    client = login(make_user("reader-rep", role="reader"))

    assert client.get("/reports/").status_code == 200
    assert client.get("/reports/overdue.csv").status_code == 200
