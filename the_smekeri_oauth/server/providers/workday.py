"""
Workday HCM provider — SCIM 2.0 integration for workforce lifecycle management.

Expected credentials dict keys:
    base_url   Workday SCIM 2.0 endpoint URL
               Format: https://wd2-impl-services1.workday.com/ccx/service/scim/v2/{tenant}
               (copy from Workday: Integration → Configure Integration → SCIM endpoint)
    token      Bearer token from the ISU (Integration System User) OAuth2 client credentials flow

Workday setup steps:
  1. Create an Integration System User (ISU) in Workday security configuration
  2. Create an Integration System Security Group (ISSG) and assign the ISU
  3. Grant the ISSG the "View/Modify Worker" domain security policy
  4. Register a Client in Workday → OAuth 2.0 Clients and generate a Bearer token
  5. Use the SCIM 2.0 URL from your tenant's integration setup

SCIM docs: https://doc.workday.com/reader/vj0XoMVB~D97mYBb2V5yEw/SCIM_2_0
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

_SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


class WorkdayProvider(BaseProvider):
    name = "workday"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['token']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _find_user(self, email: str, credentials: dict) -> dict | None:
        base = credentials["base_url"].rstrip("/")
        headers = self._auth_headers(credentials)
        try:
            resp = requests.get(
                f"{base}/Users",
                headers=headers,
                params={"filter": f'emails.value eq "{email}"', "count": 1},
                timeout=30,
            )
            resp.raise_for_status()
            resources = resp.json().get("Resources", [])
            return resources[0] if resources else None
        except requests.RequestException as exc:
            logger.error("Workday user lookup error: %s", exc)
            return None

    def _patch_active(self, user_id: str, active: bool, credentials: dict) -> requests.Response:
        base = credentials["base_url"].rstrip("/")
        return requests.patch(
            f"{base}/Users/{user_id}",
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
                "workday", "revoke", True,
                f"User {email} not found in Workday — already removed or never provisioned",
            )

        user_id = user["id"]
        if not user.get("active", True):
            return ProviderResult(
                "workday", "revoke", True,
                f"Workday user {email} is already inactive", {"user_id": user_id},
            )

        try:
            resp = self._patch_active(user_id, False, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "workday", "revoke", True,
                    f"Deactivated Workday user {email} (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "workday", "revoke", False,
                f"Workday deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Workday revoke error for %s: %s", email, exc)
            return ProviderResult("workday", "revoke", False, str(exc))

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
                "workday", "grant", False,
                f"User {email} not found in Workday — hire them in HCM first, then retry",
            )

        user_id = user["id"]
        if user.get("active", False):
            return ProviderResult(
                "workday", "grant", True,
                f"Workday user {email} is already active for role '{role}'",
                {"user_id": user_id},
            )

        try:
            resp = self._patch_active(user_id, True, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "workday", "grant", True,
                    f"Activated Workday user {email} for role '{role}' (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "workday", "grant", False,
                f"Workday activate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Workday grant error for %s: %s", email, exc)
            return ProviderResult("workday", "grant", False, str(exc))
