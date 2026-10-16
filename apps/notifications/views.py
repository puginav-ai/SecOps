"""UI уведомлений: список «моих» уведомлений."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.notifications.models import Notification


@login_required
def my_notifications(request):
    notifications = Notification.objects.filter(recipient_user=request.user).order_by(
        "-created_at"
    )[:200]
    return render(request, "notifications/list.html", {"notifications": notifications})
