"""
BambooHR provider — HR onboarding platform popular among Serbian MSPs.

Expected credentials dict keys:
    api_key     BambooHR API key (generate via BambooHR → Account Settings → API Keys)
    subdomain   Company subdomain (e.g. "acmecorp" for acmecorp.bamboohr.com)

Revoke: posts a termination record to end employment — the most reliable
way to prevent access via BambooHR since there is no direct "disable login"
endpoint in the public API.

Grant: sets employment status back to "Active" via a new status table entry.

API docs: https://documentation.bamboohr.com/reference
"""
from __future__ import annotations

import datetime
import logging

import requests
from requests.auth import HTTPBasicAuth

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class BambooHRProvider(BaseProvider):
    name = "bamboohr"

    def _base_url(self, credentials: dict) -> str:
        subdomain = credentials["subdomain"]
        return f"https://api.bamboohr.com/api/gateway.php/{subdomain}/v1"

    def _auth(self, credentials: dict) -> HTTPBasicAuth:
        # BambooHR uses API key as username, any non-empty string as password
        return HTTPBasicAuth(credentials["api_key"], "x")

    def _json_headers(self) -> dict:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def _find_employee_id(self, email: str, credentials: dict) -> str | None:
        base = self._base_url(credentials)
        try:
            resp = requests.get(
                f"{base}/employees/directory",
                auth=self._auth(credentials),
                headers={"Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            for emp in resp.json().get("employees", []):
                if emp.get("workEmail", "").lower() == email.lower():
                    return str(emp["id"])
            return None
        except requests.RequestException as exc:
            logger.error("BambooHR directory lookup error: %s", exc)
            return None

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        base = self._base_url(credentials)
        emp_id = self._find_employee_id(email, credentials)
        if not emp_id:
            return ProviderResult(
                "bamboohr", "revoke", True,
                f"Employee {email} not found in BambooHR — already removed or never added",
            )

        # Post a termination to the employment history table so BambooHR
        # marks the employee as inactive and revokes system access.
        today = datetime.date.today().isoformat()
        try:
            resp = requests.post(
                f"{base}/employees/{emp_id}/tables/employmentStatus",
                auth=self._auth(credentials),
                headers=self._json_headers(),
                json={
                    "date": today,
                    "employmentStatus": "Terminated",
                    "comment": "AccessGuard automated offboarding",
                },
                timeout=30,
            )
            if resp.status_code in (200, 201, 204):
                return ProviderResult(
                    "bamboohr", "revoke", True,
                    f"Terminated BambooHR employee {email} (id={emp_id}) effective {today}",
                    {"employee_id": emp_id, "effective_date": today},
                )
            return ProviderResult(
                "bamboohr", "revoke", False,
                f"BambooHR termination failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("BambooHR revoke error for %s: %s", email, exc)
            return ProviderResult("bamboohr", "revoke", False, str(exc))

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        base = self._base_url(credentials)
        emp_id = self._find_employee_id(email, credentials)
        if not emp_id:
            return ProviderResult(
                "bamboohr", "grant", False,
                f"Employee {email} not found in BambooHR — create the HR record first",
            )

        today = datetime.date.today().isoformat()
        try:
            resp = requests.post(
                f"{base}/employees/{emp_id}/tables/employmentStatus",
                auth=self._auth(credentials),
                headers=self._json_headers(),
                json={
                    "date": today,
                    "employmentStatus": "Full-Time",
                    "comment": f"AccessGuard re-activation for role '{role}'",
                },
                timeout=30,
            )
            if resp.status_code in (200, 201, 204):
                return ProviderResult(
                    "bamboohr", "grant", True,
                    f"Re-activated BambooHR employee {email} (role='{role}', id={emp_id})",
                    {"employee_id": emp_id, "effective_date": today},
                )
            return ProviderResult(
                "bamboohr", "grant", False,
                f"BambooHR re-activation failed: {resp.status_code} {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            logger.error("BambooHR grant error for %s: %s", email, exc)
            return ProviderResult("bamboohr", "grant", False, str(exc))
