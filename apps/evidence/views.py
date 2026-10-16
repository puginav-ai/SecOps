"""UI evidence: загрузка/скачивание, журнал писем, истечение (SDD §5.4, неделя 5)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.access import module_access, role_required, user_roles
from apps.evidence.forms import EvidenceLinkForm, EvidenceUploadForm
from apps.evidence.models import EvidenceObject
from apps.evidence.services import visible_evidence

# Роли, которым разрешено скачивание файлов evidence (SDD §4: «reader» — метаданные, без файлов)
DOWNLOAD_ROLES = {"ib_admin", "ib_officer", "it_ops", "system_owner"}


def _may_download(user) -> bool:
    return bool(user.is_superuser or user_roles(user) & DOWNLOAD_ROLES)


@role_required("evidence")
def evidence_list(request):
    objects = visible_evidence(request.user).select_related("uploaded_by")
    kind = request.GET.get("kind", "")
    if kind:
        objects = objects.filter(kind=kind)
    return render(
        request,
        "evidence/list.html",
        {
            "objects": objects,
            "kind": kind,
            "kinds": EvidenceObject.Kind.choices,
            "can_edit": module_access(request.user, "evidence") == "rw",
            "may_download": _may_download(request.user),
        },
    )


@role_required("evidence", "rw")
def evidence_upload(request):
    form = EvidenceUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        evidence = form.save(commit=False)
        evidence.uploaded_by = request.user
        evidence.save()
        messages.success(request, f"Evidence «{evidence.title}» загружено")
        return redirect("evidence:detail", pk=evidence.pk)
    return render(request, "evidence/upload.html", {"form": form})


@role_required("evidence")
def evidence_detail(request, pk: int):
    evidence = get_object_or_404(
        visible_evidence(request.user).select_related("uploaded_by"), pk=pk
    )
    links = evidence.links.all()
    return render(
        request,
        "evidence/detail.html",
        {
            "object": evidence,
            "links": links,
            "form": EvidenceLinkForm(evidence=evidence),
            "can_edit": module_access(request.user, "evidence") == "rw",
            "may_download": _may_download(request.user),
        },
    )


@role_required("evidence")
def evidence_download(request, pk: int):
    if not _may_download(request.user):
        raise PermissionDenied
    evidence = get_object_or_404(visible_evidence(request.user), pk=pk)
    file_handle = evidence.file.open("rb")
    filename = evidence.filename or Path(evidence.file.name).name
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@role_required("evidence", "rw")
def evidence_link_add(request, pk: int):
    evidence = get_object_or_404(visible_evidence(request.user), pk=pk)
    form = EvidenceLinkForm(request.POST, evidence=evidence)
    if form.is_valid():
        link = form.save(commit=False)
        link.evidence = evidence
        link.save()
        messages.success(request, "Связь добавлена")
    else:
        messages.error(request, f"Не удалось привязать: {form.errors.as_text()}")
    return redirect("evidence:detail", pk=evidence.pk)


@role_required("evidence")
def evidence_expiring(request):
    """Отчёт «evidence истекает через N дней» (SDD §5.4)."""
    try:
        days = int(request.GET.get("days", "30") or 30)
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    limit = timezone.localdate() + timedelta(days=days)
    objects = (
        visible_evidence(request.user)
        .filter(valid_until__isnull=False, valid_until__lte=limit)
        .order_by("valid_until")
    )
    return render(
        request,
        "evidence/expiring.html",
        {"objects": objects, "days": days, "limit": limit},
    )
