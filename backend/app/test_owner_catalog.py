"""Owner service-catalog integration: Owner booking_services is the single source of truth."""

import pathlib

import pytest

from . import models, owner_catalog
from .test_main import TestingSessionLocal, checkin, client, fake_emails, register, reset_db, today_local  # noqa: F401  (autouse fixtures come from test_main)


class TestOwnerCatalogClient:

    def test_services_listed_from_owner(self):
        r = client.get("/services")
        assert r.status_code == 200
        assert [(s["id"], s["name"]) for s in r.json()] == [(10, "Gel Manicure"), (11, "Classic Pedicure"), (12, "Acrylic Full Set")]

    def test_fetch_sends_base_and_token(self, owner):
        client.get("/services")
        assert owner.calls == [("http://owner.test", "test-internal-token")]

    @pytest.mark.parametrize("raw", [
        {"not": "a list"},
        [{"id": "10", "name": "x", "is_active": True}],
        [{"id": 10, "name": "", "is_active": True}],
        [{"id": 10, "name": "x", "is_active": "yes"}],
        [{"id": 10, "name": "a", "is_active": True}, {"id": 10, "name": "b", "is_active": True}],
        ["junk"],
    ])
    def test_malformed_response_fails_safely(self, owner, raw):
        owner.raw = raw
        assert client.get("/services").status_code == 503

    def test_unconfigured_fails_safely(self, monkeypatch):
        monkeypatch.delenv("OWNER_API_BASE")
        assert client.get("/services").status_code == 503

    def test_cache_avoids_refetch_until_expiry(self, owner):
        client.get("/services")
        client.get("/services")
        assert len(owner.calls) == 1
        owner.advance(46)
        client.get("/services")
        assert len(owner.calls) == 2

    def test_forced_refresh_bypasses_cache(self, owner):
        owner_catalog.catalog.get_services()
        owner.advance(6)  # past the force-refresh floor, inside the TTL
        owner_catalog.catalog.get_services(force_refresh=True)
        assert len(owner.calls) == 2

    def test_forced_refresh_is_rate_limited(self, owner):
        owner_catalog.catalog.get_services()
        owner_catalog.catalog.get_services(force_refresh=True)
        assert len(owner.calls) == 1

    def test_owner_down_serves_recent_cache_then_503(self, owner):
        assert client.get("/services").status_code == 200
        owner.error = OSError("down")
        owner.advance(100)  # TTL expired, still inside the stale window
        assert client.get("/services").status_code == 200
        owner.advance(400)  # beyond the stale window
        r = client.get("/services")
        assert r.status_code == 503
        assert "front desk" in r.json()["detail"]

    def test_owner_down_without_cache_has_no_hardcoded_fallback(self, owner):
        owner.error = OSError("down")
        assert client.get("/services").status_code == 503

    def test_inactive_entries_are_never_listed(self, owner):
        owner.raw = [
            {"id": 1, "name": "Live", "is_active": True},
            {"id": 2, "name": "Dead", "is_active": False},
        ]
        assert [s["name"] for s in client.get("/services").json()] == ["Live"]


class TestOwnerServiceIds:

    def test_checkin_stores_and_returns_ids(self):
        register("5550000001", "Alice", "1990-03-15")
        r = checkin("5550000001", [10, 12])
        assert r.status_code == 200
        assert r.json()["selected_service_ids"] == [10, 12]
        assert r.json()["selected_services"] == ["Gel Manicure", "Acrylic Full Set"]

    def test_today_checkins_has_ids_and_legacy_names(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001", [10, 12])
        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["service_ids"] == [10, 12]
        assert item["services"] == ["Gel Manicure", "Acrylic Full Set"]

    def test_legacy_name_only_visit_still_works(self):
        register("5550000001", "Alice", "1990-03-15")
        db = TestingSessionLocal()
        customer = db.query(models.Customer).one()
        svc = models.Service(name="Old Legacy Service", is_active=True)
        visit = models.Visit(customer_id=customer.id, visit_date=today_local())
        db.add_all([svc, visit])
        db.flush()
        db.add(models.VisitService(visit_id=visit.id, service_id=svc.id))
        db.commit()
        db.close()

        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["services"] == ["Old Legacy Service"]
        assert item["service_ids"] == []
        hist = client.get("/customers/5550000001/visits").json()["visits"][0]
        assert hist["services"] == ["Old Legacy Service"]
        assert client.get("/queue-status").json()["checkins"][0]["services"] == ["Old Legacy Service"]

    def test_rename_keeps_id_and_new_catalog_shows_new_name(self, owner):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1990-03-15")
        checkin("5550000001", [10])

        owner.rename(10, "Gel Polish Manicure")
        owner.advance(46)  # cache refresh
        listed = {s["id"]: s["name"] for s in client.get("/services").json()}
        assert listed[10] == "Gel Polish Manicure"

        r = checkin("5550000002", [10])
        assert r.json()["selected_service_ids"] == [10]
        assert r.json()["selected_services"] == ["Gel Polish Manicure"]
        items = client.get("/today-checkins").json()["checkins"]
        assert [i["service_ids"] for i in items] == [[10], [10]]  # same stable id before and after
        assert items[0]["services"] == ["Gel Manicure"]  # historical snapshot untouched

    def test_deactivated_service_disappears_but_history_stays(self, owner):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1990-03-15")
        checkin("5550000001", [10])

        owner.deactivate(10)
        owner.advance(46)
        assert 10 not in [s["id"] for s in client.get("/services").json()]
        assert client.get("/customers/5550000001/visits").json()["visits"][0]["services"] == ["Gel Manicure"]
        assert client.get("/today-checkins").json()["checkins"][0]["service_ids"] == [10]
        assert checkin("5550000002", [10]).status_code == 404

    def test_stale_selection_forces_refresh_and_never_falls_back_by_name(self, owner):
        register("5550000001", "Alice", "1990-03-15")
        client.get("/services")  # primes the cache with id 10 active
        owner.deactivate(10)
        owner.rename(11, "Gel Manicure")  # another service now carries the old name
        owner.advance(6)  # allows the forced refresh

        r = checkin("5550000001", [10])
        assert r.status_code == 404
        assert "reselect" in r.json()["detail"].lower()
        assert len(owner.calls) == 2  # forced refresh happened
        # nothing was recorded, and id 10 was not remapped to id 11
        assert client.get("/today-checkins").json()["checkins"] == []

    def test_owner_down_blocks_checkin_without_hardcoded_fallback(self, owner):
        register("5550000001", "Alice", "1990-03-15")
        owner.error = OSError("down")
        assert checkin("5550000001", [10]).status_code == 503
        assert client.get("/today-checkins").json()["checkins"] == []

    def test_internal_token_never_in_public_responses(self, owner):
        bodies = [client.get("/services").text, client.get("/queue-status").text]
        owner.error = OSError("boom")
        owner_catalog.catalog.clear()
        bodies.append(client.get("/services").text)
        assert all("test-internal-token" not in b for b in bodies)

    def test_frontend_has_no_owner_token_or_owner_url(self):
        frontend = pathlib.Path(__file__).resolve().parents[2] / "frontend"
        text = "".join(p.read_text(encoding="utf-8") for p in frontend.iterdir() if p.is_file())
        for needle in ("X-Internal-Service-Token", "CHECKIN_INTERNAL_SERVICE_TOKEN", "/internal/services", "OWNER_API_BASE"):
            assert needle not in text


class TestHardening:

    def test_more_services_than_owner_accepts_is_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.post("/customers/check-in/5550000001", json={"selected_service_ids": list(range(1, 22))})
        assert r.status_code == 422

    def test_redirects_are_not_followed(self):
        import urllib.request
        handler = owner_catalog._NoRedirect()
        req = urllib.request.Request("http://owner.test/internal/services", headers={"X-Internal-Service-Token": "t"})
        assert handler.redirect_request(req, None, 302, "Found", {}, "http://evil.test/") is None

    def test_non_http_scheme_is_refused(self):
        with pytest.raises(ValueError):
            owner_catalog._http_fetch("file:///etc", "t")
