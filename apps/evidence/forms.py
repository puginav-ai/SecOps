"""Формы evidence: загрузка (whitelist/лимит, поля письма) и связи (неделя 5)."""

from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings

from apps.evidence.models import EvidenceLink, EvidenceObject


class EvidenceUploadForm(forms.ModelForm):
    class Meta:
        model = EvidenceObject
        fields = [
            "title",
            "kind",
            "file",
            "issued_at",
            "valid_until",
            "confidentiality",
            "letter_direction",
            "letter_number",
            "letter_date",
            "correspondent",
            "reply_due_at",
            "reply_status",
        ]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = Path(uploaded.name).suffix.lower().lstrip(".")
        allowed = {item.lower().lstrip(".") for item in settings.EVIDENCE_ALLOWED_EXTENSIONS}
        if extension not in allowed:
            raise forms.ValidationError(f"Недопустимый тип файла: «.{extension}»")
        limit = settings.EVIDENCE_MAX_MB * 1024 * 1024
        if uploaded.size > limit:
            raise forms.ValidationError(f"Файл больше {settings.EVIDENCE_MAX_MB} МБ")
        return uploaded

    def clean(self) -> dict:
        cleaned = super().clean()
        if cleaned.get("kind") == EvidenceObject.Kind.LETTER:
            for field in ("letter_direction", "letter_number", "letter_date"):
                if not cleaned.get(field):
                    self.add_error(field, "Для письма обязательны направление, номер и дата")
        return cleaned

    def save(self, commit: bool = True) -> EvidenceObject:
        instance = super().save(commit=False)
        uploaded = self.cleaned_data.get("file")
        if uploaded is not None:
            instance.mime = getattr(uploaded, "content_type", "") or ""
        if commit:
            instance.save()
        return instance


class EvidenceLinkForm(forms.ModelForm):
    """Привязка evidence к объекту; повторная связь с той же ролью отклоняется."""

    entity_type = forms.ChoiceField(
        label="Объект",
        choices=[
            ("test_run", "проверка контроля"),
            ("obligation_instance", "обязательство"),
            ("system", "ИС"),
            ("incident", "инцидент"),
        ],
    )

    class Meta:
        model = EvidenceLink
        fields = ["entity_type", "entity_id", "role"]

    def __init__(self, *args, evidence: EvidenceObject | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.evidence = evidence

    def clean(self) -> dict:
        cleaned = super().clean()
        if self.evidence is not None and all(
            cleaned.get(field) is not None for field in ("entity_type", "entity_id", "role")
        ):
            duplicate = EvidenceLink.objects.filter(
                evidence=self.evidence,
                entity_type=cleaned["entity_type"],
                entity_id=cleaned["entity_id"],
                role=cleaned["role"],
            ).exists()
            if duplicate:
                raise forms.ValidationError("Такая связь уже существует")
        return cleaned
