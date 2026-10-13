"""Read-only client for the Owner's authoritative service catalog.

Owner `booking_services` is the single source of truth. Check-In never edits it and never
persists a second catalog: this module only keeps a short-lived in-memory copy.

    Browser -> Check-In backend (this module) -> Owner GET /internal/services

The internal token is read from the environment on every call and is only ever sent to
the Owner as the X-Internal-Service-Token header. It never reaches the browser.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from .security import INTERNAL_TOKEN_HEADER

logger = logging.getLogger("nail_system.owner_catalog")

SERVICES_PATH = "/internal/services"
REQUEST_TIMEOUT_SECONDS = 5.0
# A forced refresh inside this window is served from cache, so unknown ids from the
# public check-in route cannot be used to hammer the Owner.
FORCE_REFRESH_MIN_INTERVAL_SECONDS = 5.0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class CatalogUnavailable(Exception):
    """The Owner catalog could not be fetched (or returned unusable data) and no cache is usable."""


@dataclass(frozen=True)
class CatalogService:
    id: int
    name: str
    category: Optional[str] = None
    duration_minutes: Optional[int] = None


def parse_catalog(payload) -> list[CatalogService]:
    """Validates the Owner response. Any malformed entry rejects the whole response."""
    if not isinstance(payload, list):
        raise ValueError("catalog response is not a list")

    services: list[CatalogService] = []
    seen_ids: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("catalog entry is not an object")

        service_id = item.get("id")
        if isinstance(service_id, bool) or not isinstance(service_id, int) or service_id <= 0:
            raise ValueError("catalog entry has an invalid id")
        if service_id in seen_ids:
            raise ValueError("catalog contains a duplicate id")

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("catalog entry has an invalid name")

        is_active = item.get("is_active", True)
        if not isinstance(is_active, bool):
            raise ValueError("catalog entry has an invalid is_active")

        category = item.get("category")
        if category is not None and not isinstance(category, str):
            raise ValueError("catalog entry has an invalid category")

        duration = item.get("duration_minutes")
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int)):
            raise ValueError("catalog entry has an invalid duration_minutes")

        seen_ids.add(service_id)
        if is_active:  # defensive: the default Owner response is already active-only
            services.append(
                CatalogService(
                    id=service_id,
                    name=name.strip(),
                    category=category,
                    duration_minutes=duration,
                )
            )
    return services


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: the internal token must only ever go to the configured Owner URL."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _http_fetch(base_url: str, token: str) -> object:
    if urllib.parse.urlparse(base_url).scheme not in ("http", "https"):
        raise ValueError("OWNER_API_BASE must be an http(s) URL")
    request = urllib.request.Request(
        base_url.rstrip("/") + SERVICES_PATH,
        headers={INTERNAL_TOKEN_HEADER: token, "Accept": "application/json"},
        method="GET",
    )
    with _opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # nosec - configured Owner URL
        return json.loads(response.read().decode("utf-8"))


class OwnerCatalogClient:
    def __init__(self, fetcher: Callable[[str, str], object] = _http_fetch, clock: Callable[[], float] = time.monotonic):
        self._fetcher = fetcher
        self._clock = clock
        self._lock = threading.Lock()
        self._services: Optional[list[CatalogService]] = None
        self._fetched_at = 0.0

    # Read at call time so tests / deployments can change them without a restart.
    @staticmethod
    def ttl_seconds() -> float:
        return _env_float("OWNER_CATALOG_CACHE_SECONDS", 45.0)

    @staticmethod
    def max_stale_seconds() -> float:
        """How long the last good catalog may be served while the Owner is unreachable."""
        return _env_float("OWNER_CATALOG_MAX_STALE_SECONDS", 300.0)

    def clear(self) -> None:
        with self._lock:
            self._services = None
            self._fetched_at = 0.0

    def get_services(self, force_refresh: bool = False) -> list[CatalogService]:
        with self._lock:
            now = self._clock()
            age = now - self._fetched_at
            if self._services is not None:
                if force_refresh:
                    if age < FORCE_REFRESH_MIN_INTERVAL_SECONDS:
                        return list(self._services)
                elif age < self.ttl_seconds():
                    return list(self._services)

            try:
                self._services = self._refresh()
                self._fetched_at = now
                return list(self._services)
            except CatalogUnavailable:
                # Degraded mode: serve the last good copy only inside the stale window.
                if self._services is not None and age <= self.max_stale_seconds():
                    logger.warning("Owner catalog unavailable; serving cached copy (%.0fs old).", age)
                    return list(self._services)
                self._services = None
                raise

    def _refresh(self) -> list[CatalogService]:
        base_url = os.getenv("OWNER_API_BASE", "").strip()
        token = os.getenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "")
        if not base_url or not token:
            raise CatalogUnavailable("Owner service catalog is not configured.")
        try:
            return parse_catalog(self._fetcher(base_url, token))
        except urllib.error.HTTPError as exc:
            logger.error("Owner catalog request failed with HTTP %s.", exc.code)
            raise CatalogUnavailable("Owner service catalog is unavailable.") from None
        except (OSError, ValueError) as exc:  # URLError/timeouts are OSError; bad JSON/shape is ValueError
            logger.error("Owner catalog fetch failed: %s", type(exc).__name__)
            raise CatalogUnavailable("Owner service catalog is unavailable.") from None


catalog = OwnerCatalogClient()
