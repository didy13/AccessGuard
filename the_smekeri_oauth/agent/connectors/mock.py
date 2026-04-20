"""Mock connector for local testing — no Frappe instance needed."""
from __future__ import annotations

import logging

from .base import BaseConnector, EmployeeRecord

logger = logging.getLogger(__name__)

_MOCK_EMPLOYEES: list[dict] = [
    # demo-corp — Serbian names
    {"email": "stefan.markovic@demo-corp.com",  "name": "Stefan Marković",   "role": "Software Engineer", "status": "active"},
    {"email": "ana.jovanovic@demo-corp.com",    "name": "Ana Jovanović",     "role": "Finance Manager",   "status": "active"},
    {"email": "nikola.petrovic@demo-corp.com",  "name": "Nikola Petrović",   "role": "CEO",               "status": "active"},
    {"email": "milica.stojanovic@demo-corp.com","name": "Milica Stojanović", "role": "Accountant",        "status": "active"},
    {"email": "jovana.ilic@demo-corp.com",      "name": "Jovana Ilić",       "role": "Software Engineer", "status": "active"},
    {"email": "marko.djordjevic@demo-corp.com", "name": "Marko Đorđević",    "role": "Intern",            "status": "active"},
    {"email": "sara.radovic@demo-corp.com",     "name": "Sara Radović",      "role": "Finance Manager",   "status": "left"},
    {"email": "stefan.test@demo-corp.com",      "name": "Stefke Test",       "role": "Software Engineer", "status": "active"},
    # legacy testcorp users
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
