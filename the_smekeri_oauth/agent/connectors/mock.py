"""Mock connector for local testing — no Frappe instance needed."""
from __future__ import annotations

import logging

from .base import BaseConnector, EmployeeRecord

logger = logging.getLogger(__name__)

_MOCK_EMPLOYEES: list[dict] = [
    {"email": "alice@testcorp.com", "name": "Alice Smith",  "role": "Software Engineer", "status": "active"},
    {"email": "bob@testcorp.com",   "name": "Bob Jones",    "role": "Finance Manager",   "status": "active"},
    {"email": "carol@testcorp.com", "name": "Carol White",  "role": "Accountant",        "status": "left"},
]


class MockConnector(BaseConnector):
    """Returns a hardcoded list of employees for local dev/testing."""

    def health_check(self) -> bool:
        logger.info("MockConnector health check — always OK")
        return True

    def get_all_employees(self) -> list[EmployeeRecord]:
        logger.info("MockConnector returning %d fake employees", len(_MOCK_EMPLOYEES))
        return [
            EmployeeRecord(
                email=e["email"],
                name=e["name"],
                role=e["role"],
                status=e["status"],
            )
            for e in _MOCK_EMPLOYEES
        ]
