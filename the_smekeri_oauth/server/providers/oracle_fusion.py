"""
Oracle Fusion ERP / HCM Cloud provider — enterprise business processes.

Expected credentials dict keys:
    base_url    Oracle Cloud tenant URL (e.g. https://your-tenant.fa.oraclecloud.com)
    username    Service account username (with Security Console access)
    password    Service account password

Revoke: suspends the Oracle Fusion user account via the Oracle HCM REST API
        by setting SuspendedFlag to "Y". This blocks login to Oracle Fusion
        while preserving the user data.
Grant:  removes the suspension (SuspendedFlag = "N").

Oracle setup:
  1. Create an integration user with "IT Security Manager" duty role
  2. Grant them access to: Manage Users REST service
  3. Use the Oracle Cloud URL from your tenant confirmation email

HCM REST docs:
  https://docs.oracle.com/en/cloud/saas/human-resources/23c/farws/index.html
User Accounts:
  GET/PATCH /fscmRestApi/resources/11.13.18.05/userAccounts
"""
from __future__ import annotations

import logging

import requests
from requests.auth import HTTPBasicAuth

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

_USER_ACCOUNTS_PATH = "/fscmRestApi/resources/11.13.18.05/userAccounts"


class OracleFusionProvider(BaseProvider):
    name = "oracle_fusion_erp"

    def _auth(self, credentials: dict) -> HTTPBasicAuth:
        return HTTPBasicAuth(credentials["username"], credentials["password"])

    def _base(self, credentials: dict) -> str:
        return credentials["base_url"].rstrip("/")

    def _json_headers(self) -> dict:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def _find_user(self, email: str, credentials: dict) -> dict | None:
        base = self._base(credentials)
        try:
            resp = requests.get(
                f"{base}{_USER_ACCOUNTS_PATH}",
                auth=self._auth(credentials),
                headers=self._json_headers(),
                params={
                    "q": f"PersonEmail='{email}'",
                    "limit": 1,
                    "fields": "UserGUID,Username,PersonEmail,SuspendedFlag",
                },
                timeout=30,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            return items[0] if items else None
        except requests.RequestException as exc:
            logger.error("Oracle Fusion user lookup error: %s", exc)
            return None

    def _set_suspended(
        self, user_guid: str, suspended: bool, credentials: dict
    ) -> requests.Response:
        base = self._base(credentials)
        return requests.patch(
            f"{base}{_USER_ACCOUNTS_PATH}/{user_guid}",
            auth=self._auth(credentials),
            headers=self._json_headers(),
            json={"SuspendedFlag": "Y" if suspended else "N"},
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
                "oracle_fusion_erp", "revoke", True,
                f"Oracle Fusion user {email} not found — already removed or never added",
            )

        user_guid = user.get("UserGUID") or user.get("Username", "")
        if user.get("SuspendedFlag") == "Y":
            return ProviderResult(
                "oracle_fusion_erp", "revoke", True,
                f"Oracle Fusion user {email} is already suspended",
                {"user_guid": user_guid},
            )

        try:
            resp = self._set_suspended(user_guid, True, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "oracle_fusion_erp", "revoke", True,
                    f"Suspended Oracle Fusion user {email} (guid={user_guid})",
                    {"user_guid": user_guid},
                )
            return ProviderResult(
                "oracle_fusion_erp", "revoke", False,
                f"Oracle Fusion suspend failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Oracle Fusion revoke error for %s: %s", email, exc)
            return ProviderResult("oracle_fusion_erp", "revoke", False, str(exc))

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
                "oracle_fusion_erp", "grant", False,
                f"Oracle Fusion user {email} not found — provision them first",
            )

        user_guid = user.get("UserGUID") or user.get("Username", "")
        if user.get("SuspendedFlag") != "Y":
            return ProviderResult(
                "oracle_fusion_erp", "grant", True,
                f"Oracle Fusion user {email} is already active for role '{role}'",
                {"user_guid": user_guid},
            )

        try:
            resp = self._set_suspended(user_guid, False, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "oracle_fusion_erp", "grant", True,
                    f"Unsuspended Oracle Fusion user {email} for role '{role}' (guid={user_guid})",
                    {"user_guid": user_guid},
                )
            return ProviderResult(
                "oracle_fusion_erp", "grant", False,
                f"Oracle Fusion unsuspend failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Oracle Fusion grant error for %s: %s", email, exc)
            return ProviderResult("oracle_fusion_erp", "grant", False, str(exc))
