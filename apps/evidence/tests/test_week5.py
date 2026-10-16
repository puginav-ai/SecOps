"""Неделя 5: evidence — sha256, whitelist, письма, связи, скачивание, истечение."""

from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.evidence.forms import EvidenceUploadForm
from apps.evidence.models import EvidenceLink, EvidenceObject

pytestmark = pytest.mark.django_db


def upload_file(name: str = "act.pdf", content: bytes = b"hello-evidence") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def evidence_payload(**overrides) -> dict:
    data = {
        "title": "Акт проверки",
        "kind": EvidenceObject.Kind.ACT,
        "issued_at": "",
        "valid_until": "",
        "confidentiality": EvidenceObject.Confidentiality.INTERNAL,
        "letter_direction": "",
        "letter_number": "",
        "letter_date": "",
        "correspondent": "",
        "reply_due_at": "",
        "reply_status": "",
    }
    data.update(overrides)
    return data


def test_sha256_size_and_filename_on_save() -> None:
    evidence = EvidenceObject.objects.create(title="Акт", file=upload_file(content=b"abc123"))

    assert evidence.sha256 == hashlib.sha256(b"abc123").hexdigest()
    assert evidence.size == 6
    assert evidence.filename == "act.pdf"


def test_whitelist_rejects_unknown_extension() -> None:
    form = EvidenceUploadForm(data=evidence_payload(), files={"file": upload_file("virus.exe")})

    assert not form.is_valid()
    assert "file" in form.errors


def test_size_limit_rejected(settings) -> None:
    settings.EVIDENCE_MAX_MB = 0
    form = EvidenceUploadForm(data=evidence_payload(), files={"file": upload_file()})

    assert not form.is_valid()
    assert "file" in form.errors


def test_letter_requires_direction_number_date() -> None:
    form = EvidenceUploadForm(
        data=evidence_payload(kind=EvidenceObject.Kind.LETTER),
        files={"file": upload_file("letter.pdf")},
    )

    assert not form.is_valid()
    assert "letter_direction" in form.errors
    assert "letter_number" in form.errors
    assert "letter_date" in form.errors


def test_upload_and_download_views(client, login, make_user) -> None:
    client = login(make_user("officer-ev", role="ib_officer"))

    response = client.post(
        "/evidence/upload/",
        data={
            **evidence_payload(
                kind=EvidenceObject.Kind.LETTER,
                letter_direction="in",
                letter_number="12-И",
                letter_date="2026-10-01",
                correspondent="ФСТЭК России",
            ),
            "file": upload_file("letter.pdf"),
        },
    )

    assert response.status_code == 302
    evidence = EvidenceObject.objects.get(title="Акт проверки")

    download = client.get(f"/evidence/{evidence.pk}/download/")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == b"hello-evidence"

    reader_client = login(make_user("reader-ev", role="reader"))
    assert reader_client.get(f"/evidence/{evidence.pk}/download/").status_code == 403


def test_link_view_and_dedup(client, login, make_user) -> None:
    from apps.registry.models import Person, System

    evidence = EvidenceObject.objects.create(title="Акт2", file=upload_file())
    system = System.objects.create(
        name="ИС-Связь", owner_person=Person.objects.create(fio="Владелец Связи")
    )
    client = login(make_user("officer-link", role="ib_officer"))

    response = client.post(
        f"/evidence/{evidence.pk}/link/",
        {"entity_type": "system", "entity_id": system.pk, "role": "proof"},
    )
    assert response.status_code == 302
    assert EvidenceLink.objects.filter(
        evidence=evidence, entity_type="system", entity_id=system.pk
    ).exists()

    client.post(
        f"/evidence/{evidence.pk}/link/",
        {"entity_type": "system", "entity_id": system.pk, "role": "proof"},
        follow=True,
    )
    assert EvidenceLink.objects.filter(evidence=evidence).count() == 1


def test_expiring_report(client, login, make_user) -> None:
    EvidenceObject.objects.create(
        title="Договор скоро",
        file=upload_file("c.pdf"),
        valid_until=timezone.localdate() + timedelta(days=5),
    )
    EvidenceObject.objects.create(
        title="Договор позже",
        file=upload_file("d.pdf"),
        valid_until=timezone.localdate() + timedelta(days=300),
    )
    client = login(make_user("officer-exp", role="ib_officer"))

    body = client.get("/evidence/expiring/?days=30").content.decode()

    assert "Договор скоро" in body
    assert "Договор позже" not in body


def test_test_run_evidence_creates_proof_link() -> None:
    from apps.compliance.models import Control, ControlImplementation, TestRun
    from apps.registry.models import Person, System

    system = System.objects.create(
        name="ЛИС-Э", owner_person=Person.objects.create(fio="Владелец Э")
    )
    control = Control.objects.get(code="ANTIVIR")
    ControlImplementation.objects.create(control=control, system=system)
    test = control.tests.first()
    evidence = EvidenceObject.objects.create(title="Скан AV", file=upload_file("av.pdf"))

    run = TestRun.objects.create(test=test, system=system, result="pass", evidence=evidence)

    assert EvidenceLink.objects.filter(
        evidence=evidence, entity_type="test_run", entity_id=run.pk, role="proof"
    ).exists()
