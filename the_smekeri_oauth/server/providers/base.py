"""Abstract base for all SaaS provider integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod

# Use the shared Pydantic model so results can be serialised directly
# by FastAPI and validated by ExecutionReport without conversion.
from shared.schema import ProviderResult  # noqa: F401 — re-exported for provider modules


class BaseProvider(ABC):
    """
    Every provider module must subclass this and implement revoke() and grant().

    credentials dict keys are provider-specific and come from the encrypted
    CompanyProvider.credentials_encrypted column.
    """

    name: str = ""   # must be set on subclass

    @abstractmethod
    def revoke(self, email: str, credentials: dict) -> ProviderResult:
        """
        Revoke all OAuth grants / sessions for the given user.
        Called when an employee is terminated or loses access to this provider.
        """
        ...

    @abstractmethod
    def grant(self, email: str, role: str, credentials: dict) -> ProviderResult:
        """
        Grant access to the given user for the given role.
        Called when an employee is added or promoted to a role that includes this provider.
        """
        ...
