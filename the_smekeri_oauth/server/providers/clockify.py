"""
Clockify provider — popular time-tracking SaaS in Serbian IT agencies.

Expected credentials dict keys:
    api_key         Clockify API key (workspace admin)
    workspace_id    Clockify workspace ID

Entitlements: none currently supported — revoke deactivates the user,
grant verifies the user is active.

API docs: https://clockify.me/developers-api
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

CLOCKIFY_BASE = "https://api.clockify.me/api/v1"


class ClockifyProvider(BaseProvider):
    name = "clockify"

    def _auth_headers(self, credentials: dict) -> dict:
        return {"X-Api-Key": credentials["api_key"], "Content-Type": "application/json"}

    def _find_user(self, email: str, credentials: dict) -> dict | None:
        workspace_id = credentials["workspace_id"]
        headers = self._auth_headers(credentials)
        try:
            resp = requests.get(
                f"{CLOCKIFY_BASE}/workspaces/{workspace_id}/users",
                headers=headers,
                params={"email": email},
                timeout=30,
            )
            resp.raise_for_status()
            users = resp.json()
            for u in users:
                if u.get("email", "").lower() == email.lower():
                    return u
            return None
        except requests.RequestException as exc:
            logger.error("Clockify user lookup error: %s", exc)
            return None

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        workspace_id = credentials["workspace_id"]
        headers = self._auth_headers(credentials)

        user = self._find_user(email, credentials)
        if not user:
            return ProviderResult(
                "clockify", "revoke", True,
                f"User {email} not found in Clockify — already removed or never added",
            )

        user_id = user["id"]
        try:
            resp = requests.put(
                f"{CLOCKIFY_BASE}/workspaces/{workspace_id}/users/{user_id}",
                headers=headers,
                json={"membershipStatus": "INACTIVE"},
                timeout=30,
            )
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "clockify", "revoke", True,
                    f"Deactivated Clockify user {email} (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "clockify", "revoke", False,
                f"Clockify deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Clockify revoke error for %s: %s", email, exc)
            return ProviderResult("clockify", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        workspace_id = credentials["workspace_id"]
        headers = self._auth_headers(credentials)

        user = self._find_user(email, credentials)
        if not user:
            # Invite user to workspace
            try:
                resp = requests.post(
                    f"{CLOCKIFY_BASE}/workspaces/{workspace_id}/users",
                    headers=headers,
                    json={"emails": [email]},
                    timeout=30,
                )
                if resp.status_code in (200, 201):
                    return ProviderResult(
                        "clockify", "grant", True,
                        f"Invited {email} to Clockify workspace for role '{role}'",
                    )
                return ProviderResult(
                    "clockify", "grant", False,
                    f"Clockify invite failed: {resp.status_code} {resp.text[:200]}",
                )
            except requests.RequestException as exc:
                return ProviderResult("clockify", "grant", False, str(exc))

        user_id = user["id"]
        if user.get("membershipStatus") == "INACTIVE":
            try:
                resp = requests.put(
                    f"{CLOCKIFY_BASE}/workspaces/{workspace_id}/users/{user_id}",
                    headers=headers,
                    json={"membershipStatus": "ACTIVE"},
                    timeout=30,
                )
                if resp.status_code in (200, 204):
                    return ProviderResult(
                        "clockify", "grant", True,
                        f"Reactivated Clockify user {email} for role '{role}'",
                        {"user_id": user_id},
                    )
                return ProviderResult(
                    "clockify", "grant", False,
                    f"Clockify reactivate failed: {resp.status_code} {resp.text[:200]}",
                )
            except requests.RequestException as exc:
                return ProviderResult("clockify", "grant", False, str(exc))

        return ProviderResult(
            "clockify", "grant", True,
            f"User {email} already active in Clockify for role '{role}'",
            {"user_id": user_id},
        )
