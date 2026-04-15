"""
Zoho People provider — HR workflows platform popular among small Serbian companies.

Expected credentials dict keys:
    client_id       Zoho OAuth2 client ID (from Zoho API Console)
    client_secret   Zoho OAuth2 client secret
    refresh_token   Zoho OAuth2 refresh token (scope: ZohoPeople.employee.ALL)
    org_id          Zoho org ID (optional, for multi-org setups)
    datacenter      Zoho datacenter: "com" | "eu" | "in" | "com.au" (default: "com")

Access token is fetched automatically via the refresh token on every call so
you never need to rotate it manually. Store only the long-lived refresh token.

To obtain the initial refresh token:
  1. Go to https://api-console.zoho.com/ → Server-based Applications
  2. Add scope: ZohoPeople.employee.ALL
  3. Complete the OAuth consent flow and save the refresh_token from the response.

API docs: https://www.zoho.com/people/api/
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class ZohoProvider(BaseProvider):
    name = "zoho"

    def _datacenter(self, credentials: dict) -> str:
        return credentials.get("datacenter", "com")

    def _get_access_token(self, credentials: dict) -> str | None:
        dc = self._datacenter(credentials)
        token_url = f"https://accounts.zoho.{dc}/oauth/v2/token"
        try:
            resp = requests.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "refresh_token": credentials["refresh_token"],
                },
                timeout=30,
            )
            resp.raise_for_status()
            token = resp.json().get("access_token")
            if not token:
                logger.error("Zoho token refresh returned no access_token: %s", resp.text[:200])
            return token
        except requests.RequestException as exc:
            logger.error("Zoho token refresh error: %s", exc)
            return None

    def _auth_headers(self, access_token: str) -> dict:
        return {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json",
        }

    def _people_base(self, credentials: dict) -> str:
        dc = self._datacenter(credentials)
        return f"https://people.zoho.{dc}/people/api"

    def _find_employee(self, email: str, credentials: dict, access_token: str) -> dict | None:
        headers = self._auth_headers(access_token)
        base = self._people_base(credentials)
        try:
            resp = requests.get(
                f"{base}/forms/employee/getRecords",
                headers=headers,
                params={
                    "searchField": "Email",
                    "searchValue": email,
                    "sIndex": 1,
                    "limit": 5,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            records = data.get("response", {}).get("result", [])
            if isinstance(records, list) and records:
                return records[0]
            return None
        except requests.RequestException as exc:
            logger.error("Zoho People lookup error: %s", exc)
            return None

    def _record_id(self, employee: dict) -> str | None:
        # Zoho People returns record IDs under different keys depending on API version
        for key in ("Zoho_ID", "recordId", "Id"):
            val = employee.get(key)
            if val:
                return str(val)
        return None

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        access_token = self._get_access_token(credentials)
        if not access_token:
            return ProviderResult("zoho", "revoke", False, "Failed to obtain Zoho access token — check client credentials and refresh token")

        employee = self._find_employee(email, credentials, access_token)
        if not employee:
            return ProviderResult(
                "zoho", "revoke", True,
                f"Employee {email} not found in Zoho People — already removed or never added",
            )

        record_id = self._record_id(employee)
        if not record_id:
            return ProviderResult("zoho", "revoke", False, f"Could not determine Zoho record ID for {email}")

        headers = self._auth_headers(access_token)
        base = self._people_base(credentials)
        try:
            resp = requests.post(
                f"{base}/forms/employee/updateRecord",
                headers=headers,
                json={"recordId": record_id, "Employeestatus": "Inactive"},
                timeout=30,
            )
            if resp.status_code == 200:
                return ProviderResult(
                    "zoho", "revoke", True,
                    f"Deactivated Zoho People employee {email} (id={record_id})",
                    {"record_id": record_id},
                )
            return ProviderResult(
                "zoho", "revoke", False,
                f"Zoho deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Zoho revoke error for %s: %s", email, exc)
            return ProviderResult("zoho", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        access_token = self._get_access_token(credentials)
        if not access_token:
            return ProviderResult("zoho", "grant", False, "Failed to obtain Zoho access token — check client credentials and refresh token")

        employee = self._find_employee(email, credentials, access_token)
        if not employee:
            return ProviderResult(
                "zoho", "grant", False,
                f"Employee {email} not found in Zoho People — create the HR record first",
            )

        record_id = self._record_id(employee)
        if not record_id:
            return ProviderResult("zoho", "grant", False, f"Could not determine Zoho record ID for {email}")

        headers = self._auth_headers(access_token)
        base = self._people_base(credentials)
        try:
            resp = requests.post(
                f"{base}/forms/employee/updateRecord",
                headers=headers,
                json={"recordId": record_id, "Employeestatus": "Active"},
                timeout=30,
            )
            if resp.status_code == 200:
                return ProviderResult(
                    "zoho", "grant", True,
                    f"Activated Zoho People employee {email} for role '{role}' (id={record_id})",
                    {"record_id": record_id},
                )
            return ProviderResult(
                "zoho", "grant", False,
                f"Zoho activate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Zoho grant error for %s: %s", email, exc)
            return ProviderResult("zoho", "grant", False, str(exc))
