"""Экспорт данных в CSV и XLSX: единая точка санитизации (защита от CSV-инъекций)."""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO

from django.http import HttpResponse

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def xlsx_response(
    filename: str, header: Iterable[str], rows: Iterable[Iterable[str]]
) -> HttpResponse:
    """XLSX: значения пишутся строками — Excel формулы из текст-ячеек не исполняет."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    header = [str(cell) for cell in header]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Отчёт"
    sheet.append(header)
    for row in rows:
        sheet.append([str(cell) for cell in row])
    for index, title in enumerate(header, start=1):
        max_len = len(title)
        for row in sheet.iter_rows(min_col=index, max_col=index, min_row=2):
            for cell in row:
                max_len = max(max_len, len(str(cell.value or "")))
        sheet.column_dimensions[get_column_letter(index)].width = min(max_len + 2, 60)

    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
