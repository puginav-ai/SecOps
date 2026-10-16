"""Экспорт данных в CSV: единая точка санитизации (защита от CSV-инъекций)."""

from __future__ import annotations

from collections.abc import Iterable

from django.http import HttpResponse

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value) -> str:
    """Экранирование ячейки: формулы Excel/Calc нейтрализуются префиксом апострофа."""
    text = str(value).replace("\r", " ").replace("\n", " ").replace(";", ",")
    if text.startswith(DANGEROUS_PREFIXES):
        text = "'" + text
    return text


def csv_response(
    filename: str, header: Iterable[str], rows: Iterable[Iterable[str]]
) -> HttpResponse:
    """CSV для Excel: BOM + разделитель ';', каждая ячейка проходит csv_cell."""
    lines = [";".join(csv_cell(cell) for cell in header)]
    for row in rows:
        lines.append(";".join(csv_cell(cell) for cell in row))
    response = HttpResponse("\ufeff" + "\n".join(lines), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
