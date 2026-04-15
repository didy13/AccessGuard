"""
Informatika 365 provider — Serbian ERP/accounting platform by Informatika d.o.o.

Expected credentials dict keys:
    base_url      API base URL (provided by Informatika d.o.o. support)
                  e.g. https://api.informatika365.rs/api/v1
    api_key       API key issued by Informatika 365 admin panel
    company_id    Your company's tenant/organisation ID in the platform

Revoke: deactivates the employee account in Informatika 365, revoking access
        to payroll, accounting, and ERP modules.
Grant:  re-activates the employee account.

Integration notes:
  - Contact Informatika d.o.o. support to enable REST API access for your tenant.
  - Endpoint paths follow standard REST conventions (/employees, /users) as
    documented in their partner integration guide (available on request).
  - Authentication uses a Bearer token derived from the api_key.

If Informatika 365 exposes a different base path for your version, set base_url
to the full prefix (e.g. https://yourcompany.informatika365.rs/integration/v2).
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class Informatika365Provider(BaseProvider):
    name = "informatika365"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "Authorization": f"Bearer {credentials['api_key']}",
            "X-Company-ID": str(credentials.get("company_id", "")),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _base(self, credentials: dict) -> str:
        return credentials["base_url"].rstrip("/")

    def _find_employee(self, email: str, credentials: dict) -> dict | None:
        base = self._base(credentials)
        headers = self._auth_headers(credentials)
        # Try direct email search first
        try:
            resp = requests.get(
                f"{base}/employees",
                headers=headers,
                params={"email": email, "limit": 1},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                employees = data if isinstance(data, list) else data.get("data", data.get("employees", []))
                for emp in employees:
                    if emp.get("email", "").lower() == email.lower():
                        return emp
                if employees and isinstance(employees, list) and len(employees) == 1:
                    return employees[0]
            # Fall back to users endpoint
            resp2 = requests.get(
                f"{base}/users",
                headers=headers,
                params={"email": email, "limit": 1},
                timeout=30,
            )
            if resp2.status_code == 200:
                data2 = resp2.json()
                users = data2 if isinstance(data2, list) else data2.get("data", data2.get("users", []))
                for usr in users:
                    if usr.get("email", "").lower() == email.lower():
                        return usr
            return None
        except requests.RequestException as exc:
            logger.error("Informatika 365 employee lookup error: %s", exc)
            return None

    def _set_active(self, record: dict, active: bool, credentials: dict) -> requests.Response:
        base = self._base(credentials)
        headers = self._auth_headers(credentials)
        record_id = record.get("id") or record.get("employeeId") or record.get("userId")
        # Try employees endpoint first, fall back to users
        endpoint = f"{base}/employees/{record_id}"
        resp = requests.patch(
            endpoint,
            headers=headers,
            json={"active": active, "status": "active" if active else "inactive"},
            timeout=30,
        )
        if resp.status_code == 404:
            resp = requests.patch(
                f"{base}/users/{record_id}",
                headers=headers,
                json={"active": active, "status": "active" if active else "inactive"},
                timeout=30,
            )
        return resp

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        employee = self._find_employee(email, credentials)
        if not employee:
            return ProviderResult(
                "informatika365", "revoke", True,
                f"Employee {email} not found in Informatika 365 — already removed or never added",
            )

        record_id = employee.get("id") or employee.get("employeeId") or employee.get("userId")
        try:
            resp = self._set_active(employee, False, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "informatika365", "revoke", True,
                    f"Deactivated Informatika 365 employee {email} (id={record_id})",
                    {"record_id": record_id},
                )
            return ProviderResult(
                "informatika365", "revoke", False,
                f"Informatika 365 deactivate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Informatika 365 revoke error for %s: %s", email, exc)
            return ProviderResult("informatika365", "revoke", False, str(exc))

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
                "informatika365", "grant", False,
                f"Employee {email} not found in Informatika 365 — create their record first",
            )

        record_id = employee.get("id") or employee.get("employeeId") or employee.get("userId")
        try:
            resp = self._set_active(employee, True, credentials)
            if resp.status_code in (200, 204):
                return ProviderResult(
                    "informatika365", "grant", True,
                    f"Activated Informatika 365 employee {email} for role '{role}' (id={record_id})",
                    {"record_id": record_id},
                )
            return ProviderResult(
                "informatika365", "grant", False,
                f"Informatika 365 activate failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Informatika 365 grant error for %s: %s", email, exc)
            return ProviderResult("informatika365", "grant", False, str(exc))
