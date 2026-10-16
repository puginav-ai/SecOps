"""Формы evidence: загрузка (whitelist/лимит, поля письма) и связи (неделя 5)."""

from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings

from apps.core.access import is_owner_only
from apps.evidence.models import EvidenceLink, EvidenceObject

# MIME фиксируем сами по расширению — клиентскому content-type не доверяем
MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "rtf": "application/rtf",
    "txt": "text/plain",
    "log": "text/plain",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "xml": "application/xml",
    "json": "application/json",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "zip": "application/zip",
    "rar": "application/vnd.rar",
    "7z": "application/x-7z-compressed",
    "cfg": "text/plain",
}


def mime_for(filename: str) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    return MIME_BY_EXTENSION.get(extension, "application/octet-stream")


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
            instance.mime = mime_for(uploaded.name)
        if commit:
            instance.save()
        return instance


class EvidenceLinkForm(forms.ModelForm):
    """Привязка evidence к объекту; повторы и чужие объекты отклоняются."""

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

    def __init__(
        self,
        *args,
        evidence: EvidenceObject | None = None,
        user=None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.evidence = evidence
        self.user = user

    def _entity_exists(self, entity_type: str, entity_id: int) -> bool:
        from apps.compliance.models import TestRun
        from apps.obligations.models import ObligationInstance
        from apps.registry.models import System

        models_by_type = {
            "test_run": TestRun,
            "obligation_instance": ObligationInstance,
            "system": System,
        }
        model = models_by_type.get(entity_type)
        if model is None:  # «incident» — модуль ещё не реализован
            return True
        objects = model.objects.filter(pk=entity_id)
        if entity_type == "system" and self.user is not None and is_owner_only(self.user):
            person = getattr(self.user, "person", None)
            objects = objects.filter(owner_person=person) if person else objects.none()
        return objects.exists()

    def clean(self) -> dict:
        cleaned = super().clean()
        entity_type = cleaned.get("entity_type")
        entity_id = cleaned.get("entity_id")
        role = cleaned.get("role")
        if entity_type and entity_id is not None and role:
            if not self._entity_exists(entity_type, entity_id):
                self.add_error("entity_id", "Объект не найден или недоступен")
            if (
                self.evidence is not None
                and EvidenceLink.objects.filter(
                    evidence=self.evidence,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    role=role,
                ).exists()
            ):
                raise forms.ValidationError("Такая связь уже существует")
        return cleaned
