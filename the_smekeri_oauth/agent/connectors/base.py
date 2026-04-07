"""Abstract base for employee database connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmployeeRecord:
    """Normalised employee record, independent of the source system."""

    email: str
    name: str
    role: str          # designation / job title
    status: str        # "active" | "left"
    employee_id: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.email = self.email.lower().strip()


class BaseConnector(ABC):
    """Every HR / ERP connector must implement this interface."""

    @abstractmethod
    def get_all_employees(self) -> list[EmployeeRecord]:
        """Return the current snapshot of all employees."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True when the data source is reachable."""
        ...
