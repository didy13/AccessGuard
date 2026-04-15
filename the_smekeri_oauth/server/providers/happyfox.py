"""
HappyFox provider — IT/HR helpdesk platform.

Expected credentials dict keys:
    api_key     HappyFox API key
    api_secret  HappyFox account/API secret (used as HTTP Basic auth password)
    subdomain   HappyFox subdomain (e.g. "company" for company.happyfox.com)

Revoke: marks the staff member as inactive so they can no longer access the
        helpdesk or receive ticket assignments.
Grant:  re-activates the staff member.

API docs: https://developer.happyfox.com/v2/docs/
Base URL:  https://{subdomain}.happyfox.com/api/1.1/json/
"""
from __future__ import annotations

import logging

import requests
from requests.auth import HTTPBasicAuth

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class HappyFoxProvider(BaseProvider):
    name = "happyfox"

    def _base_url(self, credentials: dict) -> str:
        return f"https://{credentials['subdomain']}.happyfox.com/api/1.1/json"

    def _auth(self, credentials: dict) -> HTTPBasicAuth:
        return HTTPBasicAuth(credentials["api_key"], credentials["api_secret"])

    def _json_headers(self) -> dict:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def _find_staff(self, email: str, credentials: dict) -> dict | None:
        base = self._base_url(credentials)
        page = 1
        while True:
            try:
                resp = requests.get(
                    f"{base}/staff/",
                    auth=self._auth(credentials),
                    headers=self._json_headers(),
                    params={"page": page, "size": 50},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                staff_list = data.get("data", [])
                if not staff_list:
                    return None
                for staff in staff_list:
                    if staff.get("email", "").lower() == email.lower():
                        return staff
                page_info = data.get("page_info", {})
                if not page_info.get("has_next", False):
                    return None
                page += 1
            except requests.RequestException as exc:
                logger.error("HappyFox staff lookup error: %s", exc)
                return None

    def _update_staff(self, staff_id: int, active: bool, credentials: dict) -> requests.Response:
        base = self._base_url(credentials)
        return requests.put(
            f"{base}/staff/{staff_id}/",
            auth=self._auth(credentials),
            headers=self._json_headers(),
            json={"is_active": active},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        staff = self._find_staff(email, credentials)
        if not staff:
            return ProviderResult(
                "happyfox", "revoke", True,
                f"HappyFox staff {email} not found — already removed or never added",
            )

        staff_id = staff.get("id")
        if not staff.get("is_active", True):
            return ProviderResult(
                "happyfox", "revoke", True,
                f"HappyFox staff {email} is already inactive",
                {"staff_id": staff_id},
            )

        try:
            resp = self._update_staff(staff_id, False, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "happyfox", "revoke", True,
                    f"Deactivated HappyFox staff {email} (id={staff_id})",
                    {"staff_id": staff_id},
                )
            return ProviderResult(
                "happyfox", "revoke", False,
                f"HappyFox deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("HappyFox revoke error for %s: %s", email, exc)
            return ProviderResult("happyfox", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        staff = self._find_staff(email, credentials)
        if not staff:
            return ProviderResult(
                "happyfox", "grant", False,
                f"HappyFox staff {email} not found — create their account first",
            )

        staff_id = staff.get("id")
        if staff.get("is_active", False):
            return ProviderResult(
                "happyfox", "grant", True,
                f"HappyFox staff {email} is already active for role '{role}'",
                {"staff_id": staff_id},
            )

        try:
            resp = self._update_staff(staff_id, True, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "happyfox", "grant", True,
                    f"Re-activated HappyFox staff {email} for role '{role}' (id={staff_id})",
                    {"staff_id": staff_id},
                )
            return ProviderResult(
                "happyfox", "grant", False,
                f"HappyFox re-activation failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("HappyFox grant error for %s: %s", email, exc)
            return ProviderResult("happyfox", "grant", False, str(exc))
