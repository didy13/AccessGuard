"""
Microsoft 365 / Azure AD provider.

Expected credentials dict keys:
    tenant_id       Azure AD tenant ID
    client_id       App registration client ID
    client_secret   App registration client secret
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class MicrosoftProvider(BaseProvider):
    name = "microsoft"

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _get_access_token(self, credentials: dict) -> str | None:
        url = TOKEN_URL.format(tenant_id=credentials["tenant_id"])
        data = {
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
        }
        try:
            resp = requests.post(url, data=data, timeout=30)
            resp.raise_for_status()
            return resp.json()["access_token"]
        except requests.RequestException as exc:
            logger.error("Microsoft token error: %s", exc)
            return None

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def revoke(self, email: str, credentials: dict) -> ProviderResult:
        token = self._get_access_token(credentials)
        if not token:
            return ProviderResult("microsoft", "revoke", False, "Failed to obtain access token")

        headers = self._auth_headers(token)
        errors: list[str] = []

        # 1. Revoke all active sign-in sessions
        try:
            resp = requests.post(
                f"{GRAPH_BASE}/users/{email}/revokeSignInSessions",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 404:
                return ProviderResult("microsoft", "revoke", True, f"User {email} not found in Azure AD — account already removed")
            if resp.status_code != 200:
                errors.append(f"revokeSignInSessions: {resp.status_code} {resp.text[:100]}")
        except requests.RequestException as exc:
            errors.append(f"revokeSignInSessions exception: {exc}")

        # 2. Delete all delegated OAuth permission grants
        try:
            list_resp = requests.get(
                f"{GRAPH_BASE}/users/{email}/oauth2PermissionGrants",
                headers=headers,
                timeout=30,
            )
            if list_resp.status_code == 404:
                return ProviderResult("microsoft", "revoke", True, f"User {email} not found in Azure AD — account already removed")
            if list_resp.status_code == 200:
                for grant in list_resp.json().get("value", []):
                    grant_id = grant.get("id")
                    if not grant_id:
                        continue
                    del_resp = requests.delete(
                        f"{GRAPH_BASE}/oauth2PermissionGrants/{grant_id}",
                        headers=headers,
                        timeout=30,
                    )
                    if del_resp.status_code != 204:
                        errors.append(f"delete grant {grant_id}: {del_resp.status_code}")
            else:
                errors.append(f"list grants: {list_resp.status_code} {list_resp.text[:100]}")
        except requests.RequestException as exc:
            errors.append(f"oauth grants exception: {exc}")

        if errors:
            return ProviderResult("microsoft", "revoke", False, "; ".join(errors))
        return ProviderResult("microsoft", "revoke", True, f"Sessions and grants revoked for {email}")

    def grant(self, email: str, role: str, credentials: dict) -> ProviderResult:
        """
        Grant access.  In most environments, account creation and licensing
        is managed elsewhere.  This method can be extended to assign groups
        or licenses via the Graph API.
        """
        token = self._get_access_token(credentials)
        if not token:
            return ProviderResult("microsoft", "grant", False, "Failed to obtain access token")

        # Placeholder: verify user exists in Azure AD
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users/{email}",
                headers=self._auth_headers(token),
                timeout=30,
            )
            if resp.status_code == 200:
                return ProviderResult(
                    "microsoft", "grant", True,
                    f"User {email} verified in Azure AD for role '{role}'"
                )
            return ProviderResult(
                "microsoft", "grant", False,
                f"User {email} not found in Azure AD: {resp.status_code}"
            )
        except requests.RequestException as exc:
            return ProviderResult("microsoft", "grant", False, str(exc))
