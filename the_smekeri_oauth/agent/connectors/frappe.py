"""Frappe / ERPNext connector."""
from __future__ import annotations

import json
import logging

import requests

from .base import BaseConnector, EmployeeRecord

logger = logging.getLogger(__name__)


class FrappeConnector(BaseConnector):
    """Reads employees from a Frappe / ERPNext instance via REST API."""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        response = requests.get(url, headers=self._headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_all_employees(self) -> list[EmployeeRecord]:
        fields = json.dumps([
            "name", "employee_name", "company_email",
            "status", "designation",
        ])
        params = {"fields": fields, "limit_page_length": 500}

        try:
            data = self._get("/api/resource/Employee", params)
        except requests.RequestException as exc:
            logger.error("Frappe API error: %s", exc)
            return []

        records: list[EmployeeRecord] = []
        for row in data.get("data", []):
            email = (row.get("company_email") or "").strip()
            if not email:
                continue
            records.append(EmployeeRecord(
                email=email,
                name=row.get("employee_name", ""),
                role=row.get("designation", ""),
                status="left" if row.get("status") == "Left" else "active",
                employee_id=row.get("name", ""),
            ))
        return records

    def health_check(self) -> bool:
        try:
            self._get("/api/method/frappe.ping")
            return True
        except Exception:
            return False
