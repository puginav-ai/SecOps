"""Формы КЗИ: создание оценки со скоупом ИС (SDD §5.6)."""

from __future__ import annotations

from django import forms

from apps.kzi.models import Assessment
from apps.registry.models import System


class AssessmentForm(forms.ModelForm):
    systems = forms.ModelMultipleChoiceField(
        label="ИС в скоупе", queryset=System.objects.order_by("name"), required=True
    )

    class Meta:
        model = Assessment
        fields = ["assessment_type", "period_label", "period_start", "period_end", "systems"]
        widgets = {
            "period_start": forms.DateInput(attrs={"type": "date"}),
            "period_end": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self) -> dict:
        cleaned = super().clean()
        start, end = cleaned.get("period_start"), cleaned.get("period_end")
        if start and end and start > end:
            self.add_error("period_end", "Конец периода раньше начала")
        return cleaned
