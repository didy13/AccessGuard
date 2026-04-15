"""
Erpag provider — cloud ERP for Serbian manufacturing and distribution companies.

Expected credentials dict keys:
    api_token   Erpag API token
                (Erpag → Administration → API Settings → Generate Token)
    company_id  Erpag company/tenant ID (visible in URL after login)

Revoke: deactivates the employee/user in Erpag, revoking access to all
        ERP modules (inventory, production, HR, etc.).
Grant:  re-activates the employee/user account.

Erpag REST API base: https://app.erpag.com/api/v1/
All requests require:
    Authorization: Bearer {api_token}
    X-Company-ID:  {company_id}

API docs: https://app.erpag.com/api/docs  (accessible after login)
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

ERPAG_BASE = "https://app.erpag.com/api/v1"


class ErpagProvider(BaseProvider):
    name = "erpag"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['api_token']}",
            "X-Company-ID": str(credentials["company_id"]),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _find_employee(self, email: str, credentials: dict) -> dict | None:
        headers = self._auth_headers(credentials)
        page = 1
        while True:
            try:
                resp = requests.get(
                    f"{ERPAG_BASE}/employees",
                    headers=headers,
                    params={"page": page, "per_page": 100, "email": email},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                employees = data if isinstance(data, list) else data.get("data", [])
                if not employees:
                    return None
                for emp in employees:
                    if emp.get("email", "").lower() == email.lower():
                        return emp
                # Check pagination
                meta = data.get("meta", {}) if isinstance(data, dict) else {}
                current = meta.get("current_page", page)
                last = meta.get("last_page", page)
                if current >= last:
                    return None
                page += 1
            except requests.RequestException as exc:
                logger.error("Erpag employee lookup error: %s", exc)
                return None

    def _set_active(self, emp_id: int, active: bool, credentials: dict) -> requests.Response:
        return requests.patch(
            f"{ERPAG_BASE}/employees/{emp_id}",
            headers=self._auth_headers(credentials),
            json={"active": active},
            timeout=30,
        )

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        employee = self._find_employee(email, credentials)
        if not employee:
            return ProviderResult(
                "erpag", "revoke", True,
                f"Erpag employee {email} not found — already removed or never added",
            )

        emp_id = employee.get("id")
        if not employee.get("active", True):
            return ProviderResult(
                "erpag", "revoke", True,
                f"Erpag employee {email} is already inactive",
                {"emp_id": emp_id},
            )

        try:
            resp = self._set_active(emp_id, False, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "erpag", "revoke", True,
                    f"Deactivated Erpag employee {email} (id={emp_id})",
                    {"emp_id": emp_id},
                )
            return ProviderResult(
                "erpag", "revoke", False,
                f"Erpag deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Erpag revoke error for %s: %s", email, exc)
            return ProviderResult("erpag", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        employee = self._find_employee(email, credentials)
        if not employee:
            return ProviderResult(
                "erpag", "grant", False,
                f"Erpag employee {email} not found — create their record in Erpag first",
            )

        emp_id = employee.get("id")
        if employee.get("active", False):
            return ProviderResult(
                "erpag", "grant", True,
                f"Erpag employee {email} is already active for role '{role}'",
                {"emp_id": emp_id},
            )

        try:
            resp = self._set_active(emp_id, True, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "erpag", "grant", True,
                    f"Re-activated Erpag employee {email} for role '{role}' (id={emp_id})",
                    {"emp_id": emp_id},
                )
            return ProviderResult(
                "erpag", "grant", False,
                f"Erpag re-activation failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Erpag grant error for %s: %s", email, exc)
            return ProviderResult("erpag", "grant", False, str(exc))
