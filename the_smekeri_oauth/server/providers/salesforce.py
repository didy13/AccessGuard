"""
Salesforce provider — CRM platform used by Serbian consulting firms.

Expected credentials dict keys:
    client_id       Connected App consumer key
    client_secret   Connected App consumer secret
    username        Salesforce user login (service/admin account)
    password        Salesforce user password
    security_token  Salesforce security token (appended to password if IP not whitelisted)
    domain          Login domain: "login" for production, "test" for sandbox (default: "login")
    api_version     Salesforce API version (default: "58.0")

Revoke: sets User.IsActive = false — immediately blocks all access.
Grant:  sets User.IsActive = true.

Connected App setup:
  1. Setup → Apps → App Manager → New Connected App
  2. Enable OAuth, add scopes: api, refresh_token
  3. Copy Consumer Key and Secret

API docs: https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class SalesforceProvider(BaseProvider):
    name = "salesforce"

    def _get_token_and_instance(self, credentials: dict) -> tuple[str, str] | tuple[None, None]:
        domain = credentials.get("domain", "login")
        token_url = f"https://{domain}.salesforce.com/services/oauth2/token"
        password = credentials["password"] + credentials.get("security_token", "")
        try:
            resp = requests.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "username": credentials["username"],
                    "password": password,
                },
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            return body["access_token"], body["instance_url"]
        except requests.RequestException as exc:
            logger.error("Salesforce auth error: %s", exc)
            return None, None

    def _auth_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _find_user_id(self, email: str, token: str, instance_url: str, credentials: dict) -> str | None:
        version = credentials.get("api_version", "58.0")
        query = f"SELECT Id FROM User WHERE Email = '{email}' AND UserType = 'Standard' LIMIT 1"
        try:
            resp = requests.get(
                f"{instance_url}/services/data/v{version}/query",
                headers=self._auth_headers(token),
                params={"q": query},
                timeout=30,
            )
            resp.raise_for_status()
            records = resp.json().get("records", [])
            return records[0]["Id"] if records else None
        except requests.RequestException as exc:
            logger.error("Salesforce user query error: %s", exc)
            return None

    def _set_active(
        self, user_id: str, active: bool, token: str, instance_url: str, credentials: dict
    ) -> requests.Response:
        version = credentials.get("api_version", "58.0")
        return requests.patch(
            f"{instance_url}/services/data/v{version}/sobjects/User/{user_id}",
            headers=self._auth_headers(token),
            json={"IsActive": active},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        token, instance_url = self._get_token_and_instance(credentials)
        if not token:
            return ProviderResult("salesforce", "revoke", False, "Failed to authenticate with Salesforce")

        user_id = self._find_user_id(email, token, instance_url, credentials)
        if not user_id:
            return ProviderResult(
                "salesforce", "revoke", True,
                f"Salesforce user {email} not found — already removed or never added",
            )

        try:
            resp = self._set_active(user_id, False, token, instance_url, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "salesforce", "revoke", True,
                    f"Deactivated Salesforce user {email} (Id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "salesforce", "revoke", False,
                f"Salesforce deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Salesforce revoke error for %s: %s", email, exc)
            return ProviderResult("salesforce", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        token, instance_url = self._get_token_and_instance(credentials)
        if not token:
            return ProviderResult("salesforce", "grant", False, "Failed to authenticate with Salesforce")

        user_id = self._find_user_id(email, token, instance_url, credentials)
        if not user_id:
            return ProviderResult(
                "salesforce", "grant", False,
                f"Salesforce user {email} not found — create their user record in Salesforce first",
            )

        try:
            resp = self._set_active(user_id, True, token, instance_url, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "salesforce", "grant", True,
                    f"Activated Salesforce user {email} for role '{role}' (Id={user_id})",
                    {"user_id": user_id},
                )
            return ProviderResult(
                "salesforce", "grant", False,
                f"Salesforce activate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Salesforce grant error for %s: %s", email, exc)
            return ProviderResult("salesforce", "grant", False, str(exc))
