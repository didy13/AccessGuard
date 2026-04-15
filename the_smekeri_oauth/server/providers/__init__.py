from .registry import registry, register_provider

# ── Core providers ────────────────────────────────────────────────────────────
from .microsoft import MicrosoftProvider
from .google import GoogleProvider

# ── HR / Payroll providers ────────────────────────────────────────────────────
from .bamboohr import BambooHRProvider
from .zoho import ZohoProvider
from .workday import WorkdayProvider
from .rippling import RipplingProvider
from .sage_hrms import SageHRMSProvider

# ── CRM / Project providers ───────────────────────────────────────────────────
from .clockify import ClockifyProvider
from .jira import JiraProvider
from .freshbooks import FreshbooksProvider
from .hubspot import HubSpotProvider
from .salesforce import SalesforceProvider

# ── ERP providers ─────────────────────────────────────────────────────────────
from .sap_s4hana import SAPProvider
from .oracle_fusion import OracleFusionProvider
from .dynamics365 import Dynamics365Provider
from .informatika365 import Informatika365Provider
from .erpag import ErpagProvider

# ── Helpdesk providers ────────────────────────────────────────────────────────
from .liveagent import LiveAgentProvider
from .groove import GrooveProvider
from .happyfox import HappyFoxProvider

# ── Generic webhook (escape hatch for unlisted vendors) ───────────────────────
from .generic_webhook import GenericWebhookProvider, GENERIC_PROVIDER_CLASSES

# ── Mock providers — safe for local testing without real credentials ───────────
from .mock import MockProvider, MockMicrosoftProvider, MockGoogleProvider

# ── Register all providers ────────────────────────────────────────────────────

# Microsoft 365 / Entra ID
register_provider("microsoft", MicrosoftProvider)
register_provider("microsoft365", MicrosoftProvider)
register_provider("azure", MicrosoftProvider)
register_provider("entra_id", MicrosoftProvider)

# Google Workspace
register_provider("google", GoogleProvider)
register_provider("google_workspace", GoogleProvider)

# HR / Payroll
register_provider("bamboohr", BambooHRProvider)
register_provider("zoho", ZohoProvider)
register_provider("zoho_people", ZohoProvider)
register_provider("workday", WorkdayProvider)
register_provider("rippling", RipplingProvider)
register_provider("sage_hrms", SageHRMSProvider)
register_provider("sage", SageHRMSProvider)
register_provider("sage_hr", SageHRMSProvider)

# CRM / Project
register_provider("clockify", ClockifyProvider)
register_provider("jira", JiraProvider)
register_provider("atlassian_jira", JiraProvider)
register_provider("freshbooks", FreshbooksProvider)
register_provider("hubspot", HubSpotProvider)
register_provider("salesforce", SalesforceProvider)

# ERP
register_provider("sap_s4hana_cloud", SAPProvider)
register_provider("sap", SAPProvider)
register_provider("oracle_fusion_erp", OracleFusionProvider)
register_provider("oracle", OracleFusionProvider)
register_provider("microsoft_dynamics_365", Dynamics365Provider)
register_provider("dynamics365", Dynamics365Provider)
register_provider("informatika365", Informatika365Provider)
register_provider("erpag", ErpagProvider)

# Helpdesk
register_provider("liveagent", LiveAgentProvider)
register_provider("groove", GrooveProvider)
register_provider("happyfox", HappyFoxProvider)

# Generic webhook
register_provider("generic_webhook", GenericWebhookProvider)
for _name, _cls in GENERIC_PROVIDER_CLASSES.items():
    register_provider(_name, _cls)

# Mock providers
register_provider("mock", MockProvider)
register_provider("mock_microsoft", MockMicrosoftProvider)
register_provider("mock_google", MockGoogleProvider)
