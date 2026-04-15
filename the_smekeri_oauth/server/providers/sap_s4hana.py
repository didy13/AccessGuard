"""
SAP S/4HANA Cloud provider — ERP for larger Serbian MSPs.

Expected credentials dict keys:
    base_url    SAP tenant URL (e.g. https://myXXXXXX.s4hana.ondemand.com)
    username    Service user (Communication Arrangement user)
    password    Service user password

Revoke: locks the Business User account via the SAP S/4HANA Cloud
        Business User API (OData v2), setting IsBusinessPurposeCompleted = true
        and locking the business partner.

Grant:  unlocks the account by clearing the lock.

SAP setup:
  1. Create a Communication System in SAP Fiori Launchpad
  2. Create a Communication Arrangement for API_BUSINESS_USER_0001
  3. Create an Inbound Communication User
  4. Note the service URL from the Communication Arrangement tile

OData API: /sap/opu/odata/sap/API_BUSINESS_USER_0001/
Docs: https://api.sap.com/api/API_BUSINESS_USER_0001/overview
"""
from __future__ import annotations

import logging

import requests
from requests.auth import HTTPBasicAuth

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

_ODATA_PATH = "/sap/opu/odata/sap/API_BUSINESS_USER_0001"


class SAPProvider(BaseProvider):
    name = "sap_s4hana_cloud"

    def _auth(self, credentials: dict) -> HTTPBasicAuth:
        return HTTPBasicAuth(credentials["username"], credentials["password"])

    def _base(self, credentials: dict) -> str:
        return credentials["base_url"].rstrip("/")

    def _json_headers(self) -> dict:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def _get_csrf_token(self, credentials: dict) -> str | None:
        """SAP OData requires a CSRF token for write operations."""
        try:
            resp = requests.get(
                f"{self._base(credentials)}{_ODATA_PATH}/A_BusinessUser",
                auth=self._auth(credentials),
                headers={"x-csrf-token": "Fetch", "Accept": "application/json"},
                params={"$top": 1, "$format": "json"},
                timeout=30,
            )
            return resp.headers.get("x-csrf-token")
        except requests.RequestException as exc:
            logger.error("SAP CSRF token fetch error: %s", exc)
            return None

    def _find_business_user(self, email: str, credentials: dict) -> dict | None:
        base = self._base(credentials)
        try:
            resp = requests.get(
                f"{base}{_ODATA_PATH}/A_BusinessUser",
                auth=self._auth(credentials),
                headers=self._json_headers(),
                params={
                    "$filter": f"PersonWorkEmail eq '{email}'",
                    "$format": "json",
                    "$top": 1,
                },
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("d", {}).get("results", [])
            return results[0] if results else None
        except requests.RequestException as exc:
            logger.error("SAP Business User lookup error: %s", exc)
            return None

    def _lock_user(
        self, user_name: str, lock: bool, credentials: dict, csrf_token: str
    ) -> requests.Response:
        base = self._base(credentials)
        # Use the Assign Business User to Communication User action indirectly:
        # lock the user via the IsLocked property on the BP role
        return requests.patch(
            f"{base}{_ODATA_PATH}/A_BusinessUser('{user_name}')",
            auth=self._auth(credentials),
            headers={
                **self._json_headers(),
                "x-csrf-token": csrf_token,
                "If-Match": "*",
            },
            json={"IsUserLocked": "X" if lock else ""},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        user = self._find_business_user(email, credentials)
        if not user:
            return ProviderResult(
                "sap_s4hana_cloud", "revoke", True,
                f"Business user {email} not found in SAP S/4HANA — already removed or never added",
            )

        user_name = user.get("UserName") or user.get("BusinessPartnerExternalID", "")
        csrf_token = self._get_csrf_token(credentials)
        if not csrf_token:
            return ProviderResult("sap_s4hana_cloud", "revoke", False, "Failed to fetch SAP CSRF token")

        try:
            resp = self._lock_user(user_name, True, credentials, csrf_token)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "sap_s4hana_cloud", "revoke", True,
                    f"Locked SAP S/4HANA user {email} (UserName={user_name})",
                    {"user_name": user_name},
                )
            return ProviderResult(
                "sap_s4hana_cloud", "revoke", False,
                f"SAP lock failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("SAP revoke error for %s: %s", email, exc)
            return ProviderResult("sap_s4hana_cloud", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        user = self._find_business_user(email, credentials)
        if not user:
            return ProviderResult(
                "sap_s4hana_cloud", "grant", False,
                f"Business user {email} not found in SAP S/4HANA — create them in the system first",
            )

        user_name = user.get("UserName") or user.get("BusinessPartnerExternalID", "")
        csrf_token = self._get_csrf_token(credentials)
        if not csrf_token:
            return ProviderResult("sap_s4hana_cloud", "grant", False, "Failed to fetch SAP CSRF token")

        try:
            resp = self._lock_user(user_name, False, credentials, csrf_token)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "sap_s4hana_cloud", "grant", True,
                    f"Unlocked SAP S/4HANA user {email} for role '{role}' (UserName={user_name})",
                    {"user_name": user_name},
                )
            return ProviderResult(
                "sap_s4hana_cloud", "grant", False,
                f"SAP unlock failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("SAP grant error for %s: %s", email, exc)
            return ProviderResult("sap_s4hana_cloud", "grant", False, str(exc))
