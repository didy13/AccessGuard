"""
Sage HR provider (formerly CakeHR, now sage.hr) — cloud HR platform.

NOTE: This integrates with Sage HR (sage.hr / cakehr.com), the cloud-based
HR product. Do not confuse with Sage HRMS (desktop), Sage 50, or Sage People.

Expected credentials dict keys:
    api_key     Sage HR API key
                (Sage HR → Settings → Integrations → API → Generate Key)

The API is keyed per-company subdomain. Revoke suspends the employee record
so they can no longer log in. Grant re-activates a suspended employee.

API docs: https://sagehr.docs.apiary.io/
Base URL:  https://api.sage.hr/v1/
"""
from __future__ import annotations

import logging

import requests

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

SAGE_HR_BASE = "https://api.sage.hr/v1"


class SageHRMSProvider(BaseProvider):
    name = "sage_hrms"

    def _auth_headers(self, credentials: dict) -> dict:
        return {
            "X-Auth-Token": credentials["api_key"],
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _find_employee(self, email: str, credentials: dict) -> dict | None:
        headers = self._auth_headers(credentials)
        page = 1
        while True:
            try:
                resp = requests.get(
                    f"{SAGE_HR_BASE}/employees",
                    headers=headers,
                    params={"page": page, "perPage": 100},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                employees = data.get("data", [])
                if not employees:
                    return None
                for emp in employees:
                    if emp.get("email", "").lower() == email.lower():
                        return emp
                # Check if there's a next page
                meta = data.get("meta", {})
                if page >= meta.get("lastPage", 1):
                    return None
                page += 1
            except requests.RequestException as exc:
                logger.error("Sage HR employee lookup error: %s", exc)
                return None

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        employee = self._find_employee(email, credentials)
        if not employee:
            return ProviderResult(
                "sage_hrms", "revoke", True,
                f"Employee {email} not found in Sage HR — already removed or never added",
            )

        emp_id = employee.get("id")
        headers = self._auth_headers(credentials)
        try:
            resp = requests.put(
                f"{SAGE_HR_BASE}/employees/{emp_id}/terminate",
                headers=headers,
                json={"terminationReason": "AccessGuard automated offboarding"},
                timeout=30,
            )
            if resp.status_code in (200, 201, 204):
                return ProviderResult(
                    "sage_hrms", "revoke", True,
                    f"Terminated Sage HR employee {email} (id={emp_id})",
                    {"employee_id": emp_id},
                )
            return ProviderResult(
                "sage_hrms", "revoke", False,
                f"Sage HR termination failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Sage HR revoke error for %s: %s", email, exc)
            return ProviderResult("sage_hrms", "revoke", False, str(exc))

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
                "sage_hrms", "grant", False,
                f"Employee {email} not found in Sage HR — add them manually first",
            )

        emp_id = employee.get("id")
        # If already active, nothing to do
        if employee.get("employmentStatus") == "active":
            return ProviderResult(
                "sage_hrms", "grant", True,
                f"Sage HR employee {email} is already active for role '{role}'",
                {"employee_id": emp_id},
            )

        headers = self._auth_headers(credentials)
        try:
            resp = requests.put(
                f"{SAGE_HR_BASE}/employees/{emp_id}",
                headers=headers,
                json={"employmentStatus": "active"},
                timeout=30,
            )
            if resp.status_code in (200, 201, 204):
                return ProviderResult(
                    "sage_hrms", "grant", True,
                    f"Re-activated Sage HR employee {email} for role '{role}' (id={emp_id})",
                    {"employee_id": emp_id},
                )
            return ProviderResult(
                "sage_hrms", "grant", False,
                f"Sage HR re-activation failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("Sage HR grant error for %s: %s", email, exc)
            return ProviderResult("sage_hrms", "grant", False, str(exc))
