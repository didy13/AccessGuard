"""
HubSpot provider — CRM/marketing platform.

Expected credentials dict keys:
    access_token   HubSpot Private App access token
                   (Settings → Integrations → Private Apps → Create / token)

Revoke: removes the employee from HubSpot as a portal user (team member).
        This revokes their HubSpot platform access but does NOT delete their
        contact record (that would destroy CRM data).
Grant:  re-invites the user as a team member with a viewer role.

Required Private App scopes:
    settings.users.read
    settings.users.write

API docs: https://developers.hubspot.com/docs/api/settings/user-provisioning
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

HS_SETTINGS_BASE = "https://api.hubspot.com/settings/v3/users"


class HubSpotProvider(BaseProvider):
    name = "hubspot"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['access_token']}",
            "Content-Type": "application/json",
        }

    def _find_user(self, email: str, credentials: dict) -> dict | None:
        headers = self._auth_headers(credentials)
        after = None
        while True:
            params: dict = {"limit": 100}
            if after:
                params["after"] = after
            try:
                resp = requests.get(HS_SETTINGS_BASE, headers=headers, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                for user in data.get("results", []):
                    if user.get("email", "").lower() == email.lower():
                        return user
                paging = data.get("paging", {}).get("next", {})
                after = paging.get("after")
                if not after:
                    return None
            except requests.RequestException as exc:
                logger.error("HubSpot user lookup error: %s", exc)
                return None

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        user = self._find_user(email, credentials)
        if not user:
            return ProviderResult(
                "hubspot", "revoke", True,
                f"HubSpot user {email} not found — already removed or never invited",
            )

        user_id = user.get("id")
        headers = self._auth_headers(credentials)
        try:
            resp = requests.delete(
                f"{HS_SETTINGS_BASE}/{user_id}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "hubspot", "revoke", True,
                    f"Removed HubSpot portal user {email} (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "hubspot", "revoke", False,
                f"HubSpot user removal failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("HubSpot revoke error for %s: %s", email, exc)
            return ProviderResult("hubspot", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        existing = self._find_user(email, credentials)
        if existing:
            return ProviderResult(
                "hubspot", "grant", True,
                f"HubSpot user {email} already exists as a portal user for role '{role}'",
                {"user_id": existing.get("id")},
            )

        headers = self._auth_headers(credentials)
        try:
            resp = requests.post(
                HS_SETTINGS_BASE,
                headers=headers,
                json={
                    "email": email,
                    "roleId": None,       # null = default role
                    "sendWelcomeEmail": True,
                },
                timeout=30,
            )
            if resp.status_code in (200, 201):
                new_user = resp.json()
                return ProviderResult(
                    "hubspot", "grant", True,
                    f"Invited {email} to HubSpot portal for role '{role}'",
                    {"user_id": new_user.get("id")},
                )
            return ProviderResult(
                "hubspot", "grant", False,
                f"HubSpot invite failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("HubSpot grant error for %s: %s", email, exc)
            return ProviderResult("hubspot", "grant", False, str(exc))
