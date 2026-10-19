"""Формы инцидентов (SDD §5.7)."""

from __future__ import annotations

from django import forms
from django.utils import timezone

from apps.evidence.models import EvidenceObject
from apps.evidence.services import visible_evidence
from apps.incidents.models import Incident, IncidentNotification


class IncidentForm(forms.ModelForm):
    detected_at = forms.DateTimeField(
        label="Обнаружен",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        initial=timezone.localtime,
    )

    class Meta:
        model = Incident
        fields = ["kind", "detected_at", "system", "severity", "description"]


class StageSendForm(forms.Form):
    """Закрытие стадии: evidence отправки обязателен (SDD §3.6)."""

    evidence = forms.ModelChoiceField(
        label="Evidence отправки",
        queryset=EvidenceObject.objects.none(),
        required=True,
        widget=forms.Select(
            attrs={"class": "form-select form-select-sm", "style": "min-width: 200px"}
        ),
    )
    channel = forms.ChoiceField(
        label="Канал отправки",
        choices=IncidentNotification.Channel.choices,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def __init__(self, *args, user=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["evidence"].queryset = (
            visible_evidence(user)
            if user is not None
            else EvidenceObject.objects.order_by("-created_at")
        )
