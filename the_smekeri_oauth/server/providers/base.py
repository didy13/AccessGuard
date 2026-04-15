"""Abstract base for all SaaS provider integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod

# Use the shared Pydantic model so results can be serialised directly
# by FastAPI and validated by ExecutionReport without conversion.
from shared.schema import ProviderResult as SchemaProviderResult


class ProviderResult(SchemaProviderResult):
    """
    Backward-compatible provider result.

    Existing provider implementations in this repository often instantiate
    ProviderResult with positional arguments. This wrapper accepts both
    positional and keyword styles while preserving the shared schema contract.
    """

    def __init__(self, *args, **kwargs):
        if args and not kwargs:
            if len(args) == 4:
                provider, action, success, message = args
                kwargs = {
                    "provider": provider,
                    "action": action,
                    "success": success,
                    "message": message,
                }
            elif len(args) == 5:
                provider, action, success, message, details = args
                kwargs = {
                    "provider": provider,
                    "action": action,
                    "success": success,
                    "message": message,
                    "details": details,
                }
        super().__init__(**kwargs)


class BaseProvider(ABC):
    """
    Every provider module must subclass this and implement revoke() and grant().

    credentials dict keys are provider-specific and come from the encrypted
    CompanyProvider.credentials_encrypted column.
    """

    name: str = ""   # must be set on subclass

    @abstractmethod
    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        """
        Revoke access for the given user.

        When ``entitlements`` is empty, providers should apply their default
        teardown (e.g. revoke OAuth grants / sessions). When non-empty, each
        dict is a provider-specific directive such as removing group membership.
        """
        ...

    @abstractmethod
    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        """
        Grant access for the given user / internal role.

        When ``entitlements`` is empty, providers may verify the principal
        exists. Non-empty lists carry structured access (groups, app roles, …).
        """
        ...
