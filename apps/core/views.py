"""UI ядра: дашборд по ролям."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.access import MODULES, ROLE_TITLES, user_modules, user_roles

MODULE_URLS: dict[str, str] = {
    "registry": "/registry/",
    "discovery": "/registry/assets/",
}


@login_required
def dashboard(request):
    modules = [
        {
            "code": code,
            "title": MODULES[code],
            "access": access,
            "url": MODULE_URLS.get(code, ""),
        }
        for code, access in user_modules(request.user)
    ]
    roles = sorted(ROLE_TITLES.get(role, role) for role in user_roles(request.user))
    return render(request, "core/dashboard.html", {"modules": modules, "roles": roles})
