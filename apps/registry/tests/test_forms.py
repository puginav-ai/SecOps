"""Форма сегмента: нормализация CIDR и сериализация окна скана (SDD §5.1–5.2)."""

from __future__ import annotations

import pytest

from apps.registry.forms import SegmentForm
from apps.registry.models import Segment, Site

pytestmark = pytest.mark.django_db


@pytest.fixture
def site() -> Site:
    return Site.objects.create(name="Площадка-Демо")


def form_data(site: Site, **overrides) -> dict:
    data = {
        "site": site.pk,
        "name": "Сегмент-Демо",
        "cidr": "10.60.3.0/24",
        "vlan": "",
        "description": "",
        "owner_person": "",
        "scan_profile": Segment.ScanProfile.PING,
        "days": ["0", "2"],
        "start": "23:00",
        "end": "05:00",
    }
    data.update(overrides)
    return data


def test_valid_form_normalizes_cidr_and_saves_window(site: Site) -> None:
    form = SegmentForm(data=form_data(site, cidr="10.60.3.7/24"))

    assert form.is_valid(), form.errors
    segment = form.save()
    assert segment.cidr == "10.60.3.0/24"
    assert segment.scan_window == {"days": [0, 2], "start": "23:00", "end": "05:00"}
    assert segment.scan_enabled is False  # скан включают осознанно


def test_invalid_cidr_rejected(site: Site) -> None:
    form = SegmentForm(data=form_data(site, cidr="10.60.3.0/33"))

    assert not form.is_valid()
    assert "cidr" in form.errors


def test_equal_window_bounds_rejected(site: Site) -> None:
    form = SegmentForm(data=form_data(site, start="23:00", end="23:00"))

    assert not form.is_valid()
    assert "end" in form.errors


def test_days_required(site: Site) -> None:
    form = SegmentForm(data=form_data(site, days=[]))

    assert not form.is_valid()
    assert "days" in form.errors


def test_edit_form_initial_comes_from_instance_window(site: Site) -> None:
    segment = Segment.objects.create(
        site=site,
        name="Сегмент-Ночной",
        cidr="10.60.4.0/24",
        scan_window={"days": [1], "start": "22:00", "end": "04:00"},
    )

    form = SegmentForm(instance=segment)

    html = form.as_p()
    assert 'value="22:00"' in html
    assert 'value="04:00"' in html
    assert html.count("checked") == 1  # выбран только вторник
