from .registry import registry, register_provider
from .microsoft import MicrosoftProvider
from .google import GoogleProvider
from .mock import MockProvider, MockMicrosoftProvider, MockGoogleProvider

# Production providers
register_provider("microsoft", MicrosoftProvider)
register_provider("google", GoogleProvider)

# Mock providers — safe for local testing without real credentials
register_provider("mock", MockProvider)
register_provider("mock_microsoft", MockMicrosoftProvider)
register_provider("mock_google", MockGoogleProvider)
