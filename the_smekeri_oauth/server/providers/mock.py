"""
Mock provider — for local development and testing only.

Accepts any credentials dict (can be empty).
Simulates a 200ms delay then returns success, letting you test the full
routing/logging pipeline without real SaaS credentials.

Register names: "mock", "mock_microsoft", "mock_google"
"""
from __future__ import annotations

import logging
import time

from .base import BaseProvider, ProviderResult

logger = logging.getLogger("accessguard.provider.mock")


class MockProvider(BaseProvider):
    name = "mock"

    def revoke(
        self,
        email: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        time.sleep(0.05)   # simulate network latency
        ents = entitlements or []
        logger.info("[MOCK] revoke(%s, entitlements=%s)", email, ents)
        return ProviderResult(
            provider=self.name,
            action="revoke",
            success=True,
            message=f"[MOCK] Access revoked for {email}",
            details={"simulated": True, "entitlements": ents},
        )

    def grant(
        self,
        email: str,
        role: str,
        credentials: dict,
        entitlements: list[dict] | None = None,
    ) -> ProviderResult:
        time.sleep(0.05)
        ents = entitlements or []
        logger.info("[MOCK] grant(%s, role=%s, entitlements=%s)", email, role, ents)
        return ProviderResult(
            provider=self.name,
            action="grant",
            success=True,
            message=f"[MOCK] Access granted to {email} for role '{role}'",
            details={"simulated": True, "role": role, "entitlements": ents},
        )


class MockMicrosoftProvider(MockProvider):
    name = "mock_microsoft"


class MockGoogleProvider(MockProvider):
    name = "mock_google"
