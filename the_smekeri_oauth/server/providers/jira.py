"""
Jira / Atlassian provider — project tracking for IT teams (Jira Cloud).

Expected credentials dict keys:
    base_url    Jira Cloud instance URL (e.g. https://yourcompany.atlassian.net)
    email       Admin account email (used for Basic auth)
    api_token   Atlassian API token (https://id.atlassian.com/manage-profile/security/api-tokens)

Revoke: suspends the Atlassian account via the Atlassian User Management API
        so the user loses access to Jira, Confluence, and all Atlassian Cloud products.
Grant:  re-enables the account.

Required: the admin account must be an Organization Admin in Atlassian Admin
(admin.atlassian.com) to call the lifecycle suspend/enable endpoints.

Atlassian User Management API:
    https://developer.atlassian.com/cloud/admin/user-management/rest/
"""
from __future__ import annotations

import logging
from base64 import b64encode

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

ATLASSIAN_ADMIN_BASE = "https://api.atlassian.com"


class JiraProvider(BaseProvider):
    name = "jira"

    def _basic_auth(self, credentials: dict) -> str:
        token = b64encode(
            f"{credentials['email']}:{credentials['api_token']}".encode()
        ).decode()
        return f"Basic {token}"

    def _jira_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": self._basic_auth(credentials),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _admin_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": self._basic_auth(credentials),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _find_account_id(self, email: str, credentials: dict) -> str | None:
        """Find Atlassian accountId by email using the Jira REST API."""
        base = credentials["base_url"].rstrip("/")
        try:
            resp = requests.get(
                f"{base}/rest/api/3/user/search",
                headers=self._jira_headers(credentials),
                params={"query": email, "maxResults": 10},
                timeout=30,
            )
            resp.raise_for_status()
            users = resp.json()
            for user in users:
                if user.get("emailAddress", "").lower() == email.lower():
                    return user.get("accountId")
            return None
        except requests.RequestException as exc:
            logger.error("Jira user search error: %s", exc)
            return None

    def _lifecycle_action(self, account_id: str, action: str, credentials: dict) -> requests.Response:
        """
        POST to Atlassian User Management lifecycle endpoint.
        action: "disable" | "enable"
        """
        return requests.post(
            f"{ATLASSIAN_ADMIN_BASE}/users/{account_id}/manage/lifecycle/{action}",
            headers=self._admin_headers(credentials),
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        account_id = self._find_account_id(email, credentials)
        if not account_id:
            return ProviderResult(
                "jira", "revoke", True,
                f"Atlassian user {email} not found — already removed or never added",
            )

        try:
            resp = self._lifecycle_action(account_id, "disable", credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "jira", "revoke", True,
                    f"Suspended Atlassian account for {email} (accountId={account_id})",
                    {"account_id": account_id},
                )
            if resp.status_code == 400 and "already" in resp.text.lower():
                return ProviderResult(
                    "jira", "revoke", True,
                    f"Atlassian account {email} is already suspended",
                    {"account_id": account_id},
                )
            return ProviderResult(
                "jira", "revoke", False,
                f"Atlassian suspend failed: {resp.status_code} {resp.text[:200]}",
                {"account_id": account_id},
            )
        except requests.RequestException as exc:
            logger.error("Jira revoke error for %s: %s", email, exc)
            return ProviderResult("jira", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        account_id = self._find_account_id(email, credentials)
        if not account_id:
            return ProviderResult(
                "jira", "grant", False,
                f"Atlassian user {email} not found — invite them to Jira first",
            )

        try:
            resp = self._lifecycle_action(account_id, "enable", credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "jira", "grant", True,
                    f"Re-enabled Atlassian account for {email} (role='{role}', accountId={account_id})",
                    {"account_id": account_id},
                )
            if resp.status_code == 400 and "already" in resp.text.lower():
                return ProviderResult(
                    "jira", "grant", True,
                    f"Atlassian account {email} is already active for role '{role}'",
                    {"account_id": account_id},
                )
            return ProviderResult(
                "jira", "grant", False,
                f"Atlassian enable failed: {resp.status_code} {resp.text[:200]}",
                {"account_id": account_id},
            )
        except requests.RequestException as exc:
            logger.error("Jira grant error for %s: %s", email, exc)
            return ProviderResult("jira", "grant", False, str(exc))
