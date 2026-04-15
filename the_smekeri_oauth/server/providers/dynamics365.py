"""
Microsoft Dynamics 365 provider — Finance/ERP via Dataverse API.

Expected credentials dict keys:
    tenant_id       Azure AD tenant ID
    client_id       App registration (service principal) client ID
    client_secret   App registration client secret
    org_url         Dynamics 365 org URL (e.g. https://myorg.crm.dynamics.com)

Revoke: sets SystemUser.isdisabled = true — blocks all D365 access immediately.
Grant:  sets SystemUser.isdisabled = false.

Azure App Registration setup:
  1. Register an app in Azure AD (same tenant as D365)
  2. Add API permission: Dynamics CRM → user_impersonation (delegated)
     OR use application permissions with a D365 application user
  3. In D365: Settings → Security → Users → New Application User
     Assign the service principal and give it the "System Administrator" role

Dataverse Web API docs:
  https://learn.microsoft.com/en-us/power-apps/developer/data-platform/webapi/overview
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class Dynamics365Provider(BaseProvider):
    name = "microsoft_dynamics_365"

    def _get_access_token(self, credentials: dict) -> str | None:
        org_url = credentials["org_url"].rstrip("/")
        url = TOKEN_URL.format(tenant_id=credentials["tenant_id"])
        try:
            resp = requests.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "scope": f"{org_url}/.default",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except requests.RequestException as exc:
            logger.error("Dynamics 365 token error: %s", exc)
            return None

    def _auth_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

    def _find_system_user(self, email: str, token: str, credentials: dict) -> dict | None:
        org_url = credentials["org_url"].rstrip("/")
        try:
            resp = requests.get(
                f"{org_url}/api/data/v9.2/systemusers",
                headers=self._auth_headers(token),
                params={
                    "$filter": f"internalemailaddress eq '{email}'",
                    "$select": "systemuserid,fullname,isdisabled",
                    "$top": 1,
                },
                timeout=30,
            )
            resp.raise_for_status()
            values = resp.json().get("value", [])
            return values[0] if values else None
        except requests.RequestException as exc:
            logger.error("Dynamics 365 user lookup error: %s", exc)
            return None

    def _set_disabled(
        self, user_id: str, disabled: bool, token: str, credentials: dict
    ) -> requests.Response:
        org_url = credentials["org_url"].rstrip("/")
        return requests.patch(
            f"{org_url}/api/data/v9.2/systemusers({user_id})",
            headers=self._auth_headers(token),
            json={"isdisabled": disabled},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        token = self._get_access_token(credentials)
        if not token:
            return ProviderResult("microsoft_dynamics_365", "revoke", False,
                "Failed to obtain Dynamics 365 access token")

        user = self._find_system_user(email, token, credentials)
        if not user:
            return ProviderResult(
                "microsoft_dynamics_365", "revoke", True,
                f"Dynamics 365 user {email} not found — already removed or never added",
            )

        user_id = user["systemuserid"]
        if user.get("isdisabled"):
            return ProviderResult(
                "microsoft_dynamics_365", "revoke", True,
                f"Dynamics 365 user {email} is already disabled",
                {"user_id": user_id},
            )

        try:
            resp = self._set_disabled(user_id, True, token, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "microsoft_dynamics_365", "revoke", True,
                    f"Disabled Dynamics 365 user {email} (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "microsoft_dynamics_365", "revoke", False,
                f"Dynamics 365 disable failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Dynamics 365 revoke error for %s: %s", email, exc)
            return ProviderResult("microsoft_dynamics_365", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        token = self._get_access_token(credentials)
        if not token:
            return ProviderResult("microsoft_dynamics_365", "grant", False,
                "Failed to obtain Dynamics 365 access token")

        user = self._find_system_user(email, token, credentials)
        if not user:
            return ProviderResult(
                "microsoft_dynamics_365", "grant", False,
                f"Dynamics 365 user {email} not found — create a SystemUser record first",
            )

        user_id = user["systemuserid"]
        if not user.get("isdisabled"):
            return ProviderResult(
                "microsoft_dynamics_365", "grant", True,
                f"Dynamics 365 user {email} is already active for role '{role}'",
                {"user_id": user_id},
            )

        try:
            resp = self._set_disabled(user_id, False, token, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "microsoft_dynamics_365", "grant", True,
                    f"Enabled Dynamics 365 user {email} for role '{role}' (id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "microsoft_dynamics_365", "grant", False,
                f"Dynamics 365 enable failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Dynamics 365 grant error for %s: %s", email, exc)
            return ProviderResult("microsoft_dynamics_365", "grant", False, str(exc))
