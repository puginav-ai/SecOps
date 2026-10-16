"""Объектная видимость evidence (устранение IDOR): владелец ИС видит только своё.

Правило: для «только владельца ИС» evidence виден, если он загружен этим пользователем
или связан с его системами (напрямую, через проверки контролей или его обязательства).
Остальные роли видят всё (в рамках доступа к модулю).
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.core.access import is_owner_only
from apps.evidence.models import EvidenceLink, EvidenceObject


def visible_evidence(user) -> QuerySet[EvidenceObject]:
    evidence = EvidenceObject.objects.all()
    if not is_owner_only(user):
        return evidence

    person = getattr(user, "person", None)
    if person is None:
        return evidence.none()

    from apps.compliance.models import TestRun
    from apps.obligations.models import ObligationInstance
    from apps.registry.models import System

    my_systems = System.objects.filter(owner_person=person).values_list("pk", flat=True)
    my_runs = TestRun.objects.filter(system__in=my_systems).values_list("pk", flat=True)
    my_obligations = ObligationInstance.objects.filter(owner_person=person).values_list(
        "pk", flat=True
    )
    linked_ids = EvidenceLink.objects.filter(
        Q(entity_type="system", entity_id__in=my_systems)
        | Q(entity_type="test_run", entity_id__in=my_runs)
        | Q(entity_type="obligation_instance", entity_id__in=my_obligations)
    ).values_list("evidence_id", flat=True)
    return evidence.filter(Q(pk__in=linked_ids) | Q(uploaded_by=user))
