"""Shared fixtures: a fake Owner so no test ever touches the network."""

import os

os.environ["CHECKIN_INTERNAL_SERVICE_TOKEN"] = "test-internal-token"

import pytest

from . import owner_catalog


class FakeOwner:
    """Stands in for Owner GET /internal/services (booking_services is the source of truth)."""

    def __init__(self):
        self.rows = [
            {"id": 10, "name": "Gel Manicure", "category": "Manicure / Pedicure", "duration_minutes": 45, "is_active": True},
            {"id": 11, "name": "Classic Pedicure", "category": "Manicure / Pedicure", "duration_minutes": 40, "is_active": True},
            {"id": 12, "name": "Acrylic Full Set", "category": "Nails", "duration_minutes": 75, "is_active": True},
        ]
        self.calls = []
        self.error = None
        self.raw = None  # overrides the payload when set
        self.now = 1000.0

    def fetch(self, base_url, token):
        self.calls.append((base_url, token))
        if self.error:
            raise self.error
        if self.raw is not None:
            return self.raw
        return [dict(r) for r in self.rows if r["is_active"]]

    def clock(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

    def rename(self, service_id, name):
        next(r for r in self.rows if r["id"] == service_id)["name"] = name

    def deactivate(self, service_id):
        next(r for r in self.rows if r["id"] == service_id)["is_active"] = False


@pytest.fixture(autouse=True)
def owner(monkeypatch):
    fake = FakeOwner()
    monkeypatch.setenv("OWNER_API_BASE", "http://owner.test")
    monkeypatch.setattr(owner_catalog.catalog, "_fetcher", fake.fetch)
    monkeypatch.setattr(owner_catalog.catalog, "_clock", fake.clock)
    owner_catalog.catalog.clear()
    yield fake
    owner_catalog.catalog.clear()
