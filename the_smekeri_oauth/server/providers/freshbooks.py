"""
Freshbooks provider — invoicing platform used by freelancers and Serbian MSPs.

Expected credentials dict keys:
    access_token   Freshbooks OAuth2 access token
                   (Freshbooks → My Apps → Developer Portal → token)
    account_id     Freshbooks account ID (visible in the URL: /accounts/{accountId})

Revoke: sets staff vis_state to 1 (deleted/inactive) so the user loses access.
Grant:  sets staff vis_state back to 0 (active).

Note: Freshbooks "staff" = team members with platform access.
      This does NOT affect client contacts — those are a separate resource.

API docs: https://www.freshbooks.com/api/start
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

FB_BASE = "https://api.freshbooks.com"
# vis_state: 0 = active, 1 = deleted/inactive
_ACTIVE = 0
_INACTIVE = 1


class FreshbooksProvider(BaseProvider):
    name = "freshbooks"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['access_token']}",
            "Content-Type": "application/json",
            "Api-Version": "alpha",
        }

    def _find_staff(self, email: str, credentials: dict) -> dict | None:
        account_id = credentials["account_id"]
        headers = self._auth_headers(credentials)
        page = 1
        while True:
            try:
                resp = requests.get(
                    f"{FB_BASE}/accounting/account/{account_id}/users/staffs",
                    headers=headers,
                    params={"page": page, "per_page": 100},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json().get("response", {}).get("result", {})
                staffs = data.get("staffs", [])
                if not staffs:
                    return None
                for staff in staffs:
                    if staff.get("email", "").lower() == email.lower():
                        return staff
                total = data.get("total", 0)
                per_page = data.get("per_page", 100)
                if page * per_page >= total:
                    return None
                page += 1
            except requests.RequestException as exc:
                logger.error("Freshbooks staff lookup error: %s", exc)
                return None

    def _update_staff_vis(
        self, staff_id: int, vis_state: int, credentials: dict
    ) -> requests.Response:
        account_id = credentials["account_id"]
        return requests.put(
            f"{FB_BASE}/accounting/account/{account_id}/users/staffs/{staff_id}",
            headers=self._auth_headers(credentials),
            json={"staff": {"vis_state": vis_state}},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        staff = self._find_staff(email, credentials)
        if not staff:
            return ProviderResult(
                "freshbooks", "revoke", True,
                f"Staff {email} not found in Freshbooks — already removed or never added",
            )

        staff_id = staff["id"]
        if staff.get("vis_state") == _INACTIVE:
            return ProviderResult(
                "freshbooks", "revoke", True,
                f"Freshbooks staff {email} is already inactive",
                {"staff_id": staff_id},
            )

        try:
            resp = self._update_staff_vis(staff_id, _INACTIVE, credentials)
            if resp.status_code == 200:
                return ProviderResult(
                    "freshbooks", "revoke", True,
                    f"Deactivated Freshbooks staff {email} (id={staff_id})",
                    {"staff_id": staff_id},
                )
            return ProviderResult(
                "freshbooks", "revoke", False,
                f"Freshbooks deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Freshbooks revoke error for %s: %s", email, exc)
            return ProviderResult("freshbooks", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        staff = self._find_staff(email, credentials)
        if not staff:
            return ProviderResult(
                "freshbooks", "grant", False,
                f"Staff {email} not found in Freshbooks — add them as a team member first",
            )

        staff_id = staff["id"]
        if staff.get("vis_state") == _ACTIVE:
            return ProviderResult(
                "freshbooks", "grant", True,
                f"Freshbooks staff {email} is already active for role '{role}'",
                {"staff_id": staff_id},
            )

        try:
            resp = self._update_staff_vis(staff_id, _ACTIVE, credentials)
            if resp.status_code == 200:
                return ProviderResult(
                    "freshbooks", "grant", True,
                    f"Re-activated Freshbooks staff {email} for role '{role}' (id={staff_id})",
                    {"staff_id": staff_id},
                )
            return ProviderResult(
                "freshbooks", "grant", False,
                f"Freshbooks re-activation failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Freshbooks grant error for %s: %s", email, exc)
            return ProviderResult("freshbooks", "grant", False, str(exc))
