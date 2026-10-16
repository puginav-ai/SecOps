"""Формы реестра: сегмент и окно скана (SDD §5.1–5.2)."""

from __future__ import annotations

import ipaddress
from datetime import time

from django import forms

from apps.registry.models import Segment, default_scan_window

WEEKDAYS = [
    (0, "Пн"),
    (1, "Вт"),
    (2, "Ср"),
    (3, "Чт"),
    (4, "Пт"),
    (5, "Сб"),
    (6, "Вс"),
]


class SegmentForm(forms.ModelForm):
    """Сегмент: CIDR нормализуется, окно скана собирается в jsonb из дней и времени."""

    days = forms.MultipleChoiceField(
        label="Дни недели", choices=WEEKDAYS, widget=forms.CheckboxSelectMultiple
    )
    start = forms.TimeField(
        label="Начало окна", widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    )
    end = forms.TimeField(
        label="Окончание окна", widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    )

    class Meta:
        model = Segment
        fields = [
            "site",
            "name",
            "cidr",
            "vlan",
            "description",
            "owner_person",
            "scan_enabled",
            "scan_profile",
        ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        window = self.instance.scan_window if self.instance.pk else default_scan_window()
        if not self.is_bound:
            self.initial.setdefault("days", [str(day) for day in window["days"]])
            self.initial.setdefault("start", time.fromisoformat(window["start"]))
            self.initial.setdefault("end", time.fromisoformat(window["end"]))

    def clean_cidr(self) -> str:
        value = self.cleaned_data["cidr"]
        try:
            return str(ipaddress.ip_network(value, strict=False))
        except ValueError:
            raise forms.ValidationError(
                "Укажите подсеть в формате CIDR, например 10.0.0.0/24"
            ) from None

    def clean(self) -> dict:
        cleaned = super().clean()
        days, start, end = cleaned.get("days"), cleaned.get("start"), cleaned.get("end")
        if days and start and end:
            if start == end:
                self.add_error("end", "Начало и окончание окна совпадают")
            else:
                cleaned["scan_window"] = {
                    "days": sorted(int(day) for day in days),
                    "start": start.strftime("%H:%M"),
                    "end": end.strftime("%H:%M"),
                }
        return cleaned

    def save(self, commit: bool = True) -> Segment:
        self.instance.scan_window = self.cleaned_data["scan_window"]
        return super().save(commit=commit)
