"""
Microsoft 365 / Azure AD provider.

Expected credentials dict keys:
    tenant_id       Azure AD tenant ID
    client_id       App registration client ID
    client_secret   App registration client secret

Entitlements (optional, extensible):

    {"type": "aad_group", "group_id": "<Azure AD group object id>"}

- ``grant`` with ``aad_group`` adds the user to that security group.
- ``revoke`` with ``aad_group`` removes the user from that group.

When ``entitlements`` is empty, ``revoke`` revokes sign-in sessions and OAuth
grants (legacy behaviour). ``grant`` verifies the user exists in the tenant.

Required Graph application permissions for group membership include
``GroupMember.ReadWrite.All`` (or equivalent) in addition to user read access.
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
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _user_object_id(self, email: str, token: str) -> str | None:
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users/{email}",
                headers=self._auth_headers(token),
                timeout=30,
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("id")
        except requests.RequestException as exc:
            logger.error("Microsoft user lookup error: %s", exc)
            return None

    def _add_group_member(self, group_id: str, user_id: str, token: str) -> str | None:
        headers = self._auth_headers(token)
        body = {"@odata.id": f"{GRAPH_BASE}/directoryObjects/{user_id}"}
        try:
            resp = requests.post(
                f"{GRAPH_BASE}/groups/{group_id}/members/$ref",
                headers=headers,
                json=body,
                timeout=30,
            )
            if resp.status_code in (204, 200):
                return None
            if resp.status_code == 400 and "already exist" in resp.text.lower():
                return None
            return f"add member to {group_id}: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as exc:
            return f"add member exception: {exc}"

    def _remove_group_member(self, group_id: str, user_id: str, token: str) -> str | None:
        headers = self._auth_headers(token)
        try:
            resp = requests.delete(
                f"{GRAPH_BASE}/groups/{group_id}/members/{user_id}/$ref",
                headers=headers,
                timeout=30,
            )
            if resp.status_code in (204, 404):
                return None
            return f"remove member from {group_id}: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as exc:
            return f"remove member exception: {exc}"

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        token = self._get_access_token(credentials)
        if not token:
            return ProviderResult("microsoft", "revoke", False, "Failed to obtain access token")

        ents = entitlements or []
        group_ops = [e for e in ents if e.get("type") == "aad_group" and e.get("group_id")]
        if ents and not group_ops:
            return ProviderResult(
                "microsoft", "revoke", False,
                "Non-empty entitlements contained no recognized Microsoft directives "
                "(expected type 'aad_group' with group_id).",
                details={"entitlements": ents},
            )

        if group_ops:
            user_id = self._user_object_id(email, token)
            if not user_id:
                return ProviderResult(
                    "microsoft", "revoke", False,
                    f"User {email} not found in Azure AD — cannot apply group entitlements",
                )
            errors: list[str] = []
            for item in group_ops:
                gid = str(item["group_id"])
                err = self._remove_group_member(gid, user_id, token)
                if err:
                    errors.append(err)
            if errors:
                return ProviderResult(
                    "microsoft", "revoke", False, "; ".join(errors),
                    details={"entitlements": ents},
                )
            return ProviderResult(
                "microsoft", "revoke", True,
                f"Removed {email} from {len(group_ops)} Azure AD group(s)",
                details={"entitlements": ents},
            )

        headers = self._auth_headers(token)
        errors: list[str] = []

        try:
            resp = requests.post(
                f"{GRAPH_BASE}/users/{email}/revokeSignInSessions",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 404:
                return ProviderResult(
                    "microsoft", "revoke", True,
                    f"User {email} not found in Azure AD — account already removed",
                )
            if resp.status_code != 200:
                errors.append(f"revokeSignInSessions: {resp.status_code} {resp.text[:100]}")
        except requests.RequestException as exc:
            errors.append(f"revokeSignInSessions exception: {exc}")

        try:
            list_resp = requests.get(
                f"{GRAPH_BASE}/users/{email}/oauth2PermissionGrants",
                headers=headers,
                timeout=30,
            )
            if list_resp.status_code == 404:
                return ProviderResult(
                    "microsoft", "revoke", True,
                    f"User {email} not found in Azure AD — account already removed",
                )
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

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        token = self._get_access_token(credentials)
        if not token:
            return ProviderResult("microsoft", "grant", False, "Failed to obtain access token")

        ents = entitlements or []
        group_ops = [e for e in ents if e.get("type") == "aad_group" and e.get("group_id")]
        if ents and not group_ops:
            return ProviderResult(
                "microsoft", "grant", False,
                "Non-empty entitlements contained no recognized Microsoft directives "
                "(expected type 'aad_group' with group_id).",
                details={"entitlements": ents},
            )

        if group_ops:
            user_id = self._user_object_id(email, token)
            if not user_id:
                return ProviderResult(
                    "microsoft", "grant", False,
                    f"User {email} not found in Azure AD: cannot add to groups",
                )
            errors: list[str] = []
            for item in group_ops:
                gid = str(item["group_id"])
                err = self._add_group_member(gid, user_id, token)
                if err:
                    errors.append(err)
            if errors:
                return ProviderResult(
                    "microsoft", "grant", False, "; ".join(errors),
                    details={"entitlements": ents},
                )
            return ProviderResult(
                "microsoft", "grant", True,
                f"Added {email} to {len(group_ops)} Azure AD group(s) for role '{role}'",
                details={"entitlements": ents},
            )

        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users/{email}",
                headers=self._auth_headers(token),
                timeout=30,
            )
            if resp.status_code == 200:
                return ProviderResult(
                    "microsoft", "grant", True,
                    f"User {email} verified in Azure AD for role '{role}'",
                )
            return ProviderResult(
                "microsoft", "grant", False,
                f"User {email} not found in Azure AD: {resp.status_code}",
            )
        except requests.RequestException as exc:
            return ProviderResult("microsoft", "grant", False, str(exc))
