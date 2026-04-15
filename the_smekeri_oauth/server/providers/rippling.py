"""
Rippling provider — global HR/payroll platform with SCIM 2.0 support.

Expected credentials dict keys:
    api_token   Rippling API token (Settings → API → Generate Token)

Rippling exposes a SCIM 2.0 endpoint at:
    https://api.rippling.com/platform/api/scim/v2.0/

Rippling also has a proprietary REST API but SCIM is the recommended path
for user lifecycle management (enable/disable employees).

Docs: https://developer.rippling.com/docs/rippling/
SCIM: https://developer.rippling.com/docs/rippling/scim
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

RIPPLING_SCIM_BASE = "https://api.rippling.com/platform/api/scim/v2.0"
_SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


class RipplingProvider(BaseProvider):
    name = "rippling"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['api_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _find_user(self, email: str, credentials: dict) -> dict | None:
        headers = self._auth_headers(credentials)
        try:
            resp = requests.get(
                f"{RIPPLING_SCIM_BASE}/Users",
                headers=headers,
                params={"filter": f'emails.value eq "{email}"', "count": 1},
                timeout=30,
            )
            resp.raise_for_status()
            resources = resp.json().get("Resources", [])
            return resources[0] if resources else None
        except requests.RequestException as exc:
            logger.error("Rippling user lookup error: %s", exc)
            return None

    def _patch_active(self, user_id: str, active: bool, credentials: dict) -> requests.Response:
        return requests.patch(
            f"{RIPPLING_SCIM_BASE}/Users/{user_id}",
            headers=self._auth_headers(credentials),
            json={
                "schemas": [_SCIM_PATCH_SCHEMA],
                "Operations": [{"op": "replace", "path": "active", "value": active}],
            },
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        user = self._find_user(email, credentials)
        if not user:
            return ProviderResult(
                "rippling", "revoke", True,
                f"User {email} not found in Rippling — already offboarded or never added",
            )

        user_id = user["id"]
        if not user.get("active", True):
            return ProviderResult(
                "rippling", "revoke", True,
                f"Rippling user {email} is already inactive", {"user_id": user_id},
            )

        try:
            resp = self._patch_active(user_id, False, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "rippling", "revoke", True,
                    f"Deactivated Rippling user {email} (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "rippling", "revoke", False,
                f"Rippling deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Rippling revoke error for %s: %s", email, exc)
            return ProviderResult("rippling", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        user = self._find_user(email, credentials)
        if not user:
            return ProviderResult(
                "rippling", "grant", False,
                f"User {email} not found in Rippling — onboard them in Rippling first",
            )

        user_id = user["id"]
        if user.get("active", False):
            return ProviderResult(
                "rippling", "grant", True,
                f"Rippling user {email} is already active for role '{role}'",
                {"user_id": user_id},
            )

        try:
            resp = self._patch_active(user_id, True, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "rippling", "grant", True,
                    f"Activated Rippling user {email} for role '{role}' (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "rippling", "grant", False,
                f"Rippling activate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Rippling grant error for %s: %s", email, exc)
            return ProviderResult("rippling", "grant", False, str(exc))
