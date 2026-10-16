"""audit_log: мидлварь мутаций, append-only, обход логинов."""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import AuditLogMiddleware
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def _middleware(response_status: int = 200) -> AuditLogMiddleware:
    return AuditLogMiddleware(lambda request: HttpResponse(status=response_status))


def _request(method: str, path: str, user=None, forwarded_for: str | None = None):
    request = RequestFactory().generic(method, path)
    request.user = user
    request.META["REMOTE_ADDR"] = "10.0.0.5"
    if forwarded_for:
        request.META["HTTP_X_FORWARDED_FOR"] = forwarded_for
    return request


def test_post_writes_audit_entry(make_user):
    user = make_user("ib", role="ib_admin")
    forwarded = "10.9.9.9, 10.0.0.1"

    _middleware()(_request("POST", "/some/mutation/", user=user, forwarded_for=forwarded))

    entry = AuditLog.objects.get()
    assert entry.actor == user
    assert entry.actor_ip == "10.9.9.9"
    assert entry.action == "POST /some/mutation/"
    assert entry.at is not None


def test_get_and_head_are_not_logged(make_user):
    user = make_user("ib2", role="ib_admin")

    _middleware()(_request("GET", "/list/", user=user))
    _middleware()(_request("HEAD", "/list/", user=user))

    assert AuditLog.objects.count() == 0


def test_anonymous_mutation_is_not_logged():
    _middleware()(_request("POST", "/anon/"))
    assert AuditLog.objects.count() == 0


def test_login_and_logout_paths_are_exempt(make_user):
    user = make_user("ib3", role="ib_admin")

    _middleware()(_request("POST", "/accounts/login/", user=user))
    _middleware()(_request("POST", "/accounts/logout/", user=user))

    assert AuditLog.objects.count() == 0


def test_failed_mutation_is_not_logged(make_user):
    user = make_user("ib4", role="ib_admin")

    _middleware(response_status=400)(_request("POST", "/bad/", user=user))
    _middleware(response_status=403)(_request("POST", "/forbidden/", user=user))

    assert AuditLog.objects.count() == 0


def test_ip_falls_back_to_remote_addr(make_user):
    user = make_user("ib5", role="ib_admin")

    _middleware()(_request("POST", "/no-proxy/", user=user))

    assert AuditLog.objects.get().actor_ip == "10.0.0.5"


def test_audit_log_is_append_only(make_user):
    entry = AuditLog.write(action="test", actor=make_user("ib6", role="ib_admin"))

    entry.action = "changed"
    with pytest.raises(RuntimeError):
        entry.save()
    with pytest.raises(RuntimeError):
        entry.delete()

    assert AuditLog.objects.get().action == "test"
