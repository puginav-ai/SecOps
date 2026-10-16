"""Валидаторы реестра: подсети (network scopes)."""

from __future__ import annotations

import ipaddress

from django.core.exceptions import ValidationError


def validate_cidr(value: str) -> None:
    """CIDR вида 10.0.0.0/24 (хост-биты допускаются и нормализуются формой)."""
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ValidationError("Укажите подсеть в формате CIDR, например 10.0.0.0/24") from exc
