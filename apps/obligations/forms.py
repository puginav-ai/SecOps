"""Формы обязательств: закрытие с evidence (SDD §5.5)."""

from __future__ import annotations

from django import forms

from apps.evidence.models import EvidenceObject
from apps.evidence.services import visible_evidence
from apps.obligations.models import ObligationInstance


class ObligationCloseForm(forms.Form):
    """Закрытие обязательства; если шаблон требует — evidence обязателен.

    Список evidence ограничивается видимым для пользователя (объектная авторизация).
    """

    evidence = forms.ModelChoiceField(
        label="Evidence закрытия",
        queryset=EvidenceObject.objects.none(),
        required=False,
    )

    def __init__(
        self,
        *args,
        instance: ObligationInstance | None = None,
        user=None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.fields["evidence"].queryset = (
            visible_evidence(user)
            if user is not None
            else EvidenceObject.objects.order_by("-created_at")
        )
        if instance is not None and instance.template.requires_closing_evidence:
            self.fields["evidence"].required = True
            self.fields[
                "evidence"
            ].help_text = "Для этого обязательства закрытие без evidence запрещено"
