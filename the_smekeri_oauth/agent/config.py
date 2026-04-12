"""Agent configuration loaded from environment variables and an optional YAML file."""
from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConnectorConfig:
    type: str = "frappe"        # "frappe" | "sql" (extensible)
    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""


@dataclass
class AgentConfig:
    # Company identity (sent in every payload)
    company_id: str = ""
    company_name: str = ""

    # Server endpoint that receives payloads
    server_url: str = ""
    server_api_key: str = ""    # shared secret for payload auth

    # How often to poll for changes (seconds)
    poll_interval: int = 900    # 15 minutes

    # Domain suffix used to detect internal Google Workspace accounts
    google_domain: str = ""

    # Maps job titles / designations → list of SaaS provider names
    # Example: {"CEO": ["microsoft", "google"], "Intern": ["microsoft"]}
    role_provider_map: dict[str, list[str]] = field(default_factory=dict)

    # Richer per-role, per-provider entitlements (takes precedence when a role matches).
    # role -> provider -> {"grant": [...], "revoke": [...]}
    # Example:
    #   "Software Engineer":
    #     microsoft:
    #       grant: [{type: aad_group, group_id: "..."}]
    #       revoke: [{type: aad_group, group_id: "..."}]
    role_access_map: dict[str, dict[str, dict[str, list]]] = field(default_factory=dict)

    # Default providers granted/revoked when no role mapping is found
    default_providers: list[str] = field(default_factory=lambda: ["microsoft"])

    # Connector settings
    connector: ConnectorConfig = field(default_factory=ConnectorConfig)

    # Path to the local state file
    state_file: str = ".agent_state.json"

    # Local dashboard web UI
    dashboard_enabled: bool = True
    dashboard_port: int = 7979


def load_config(config_path: str = "agent_config.yaml") -> AgentConfig:
    """Load config from YAML file, with env var overrides."""
    cfg = AgentConfig()

    if Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        cfg.company_id = data.get("company_id", cfg.company_id)
        cfg.company_name = data.get("company_name", cfg.company_name)
        cfg.server_url = data.get("server_url", cfg.server_url)
        cfg.server_api_key = data.get("server_api_key", cfg.server_api_key)
        cfg.poll_interval = int(data.get("poll_interval", cfg.poll_interval))
        cfg.google_domain = data.get("google_domain", cfg.google_domain)
        cfg.role_provider_map = data.get("role_provider_map", cfg.role_provider_map)
        cfg.role_access_map = data.get("role_access_map", cfg.role_access_map)
        cfg.default_providers = data.get("default_providers", cfg.default_providers)
        cfg.state_file = data.get("state_file", cfg.state_file)
        cfg.dashboard_enabled = bool(data.get("dashboard_enabled", cfg.dashboard_enabled))
        cfg.dashboard_port = int(data.get("dashboard_port", cfg.dashboard_port))

        conn = data.get("connector", {})
        cfg.connector = ConnectorConfig(
            type=conn.get("type", "frappe"),
            base_url=conn.get("base_url", ""),
            api_key=conn.get("api_key", ""),
            api_secret=conn.get("api_secret", ""),
        )

    # Environment variable overrides (take precedence over YAML)
    cfg.company_id = os.getenv("AGENT_COMPANY_ID", cfg.company_id)
    cfg.company_name = os.getenv("AGENT_COMPANY_NAME", cfg.company_name)
    cfg.server_url = os.getenv("AGENT_SERVER_URL", cfg.server_url)
    cfg.server_api_key = os.getenv("AGENT_SERVER_API_KEY", cfg.server_api_key)
    cfg.google_domain = os.getenv("AGENT_GOOGLE_DOMAIN", cfg.google_domain)
    cfg.connector.base_url = os.getenv("FRAPPE_BASE_URL", cfg.connector.base_url)
    cfg.connector.api_key = os.getenv("FRAPPE_API_KEY", cfg.connector.api_key)
    cfg.connector.api_secret = os.getenv("FRAPPE_API_SECRET", cfg.connector.api_secret)

    return cfg
