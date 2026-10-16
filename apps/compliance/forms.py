"""Формы модуля контролей (неделя 4)."""

from __future__ import annotations

from django import forms
from django.utils import timezone

from apps.compliance.models import ControlImplementation, TestRun
from apps.evidence.services import visible_evidence


class ControlImplementationForm(forms.ModelForm):
    """Правка строки матрицы; статус проверяется сервисными правилами в view."""

    class Meta:
        model = ControlImplementation
        fields = [
            "is_applicable",
            "applicability_reason",
            "status",
            "owner_person",
            "exception_note",
            "exception_evidence",
            "exception_review_at",
        ]
        widgets = {
            "exception_review_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, user=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["exception_evidence"].queryset = visible_evidence(user)


class TestRunForm(forms.ModelForm):
    """Фиксация проверки: выбор проверки контроля, результат, дата."""

    run_at = forms.DateTimeField(
        label="Когда выполнена",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        initial=timezone.localtime,
    )

    class Meta:
        model = TestRun
        fields = ["test", "run_at", "result", "evidence", "notes"]

    def __init__(
        self,
        *args,
        implementation: ControlImplementation | None = None,
        user=None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        if implementation is not None:
            self.fields["test"].queryset = implementation.control.tests.all()
        if user is not None:
            self.fields["evidence"].queryset = visible_evidence(user)
