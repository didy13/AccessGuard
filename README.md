# AccessGuard

Automated SaaS access management. Detects employee changes (termination, role change, new hire)
via a lightweight company-side agent and automatically revokes or grants access across
Microsoft 365, Google Workspace, and 20+ other providers.

> **Main documentation is in [`the_smekeri_oauth/README.md`](the_smekeri_oauth/README.md)**

---

## Quick Start (local, no credentials needed)

```bash
cd the_smekeri_oauth

# 1. Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Create server config
cat > server/.env << 'EOF'
ENCRYPTION_KEY=<run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
ADMIN_API_KEY=change-me-strong-admin-key
AUTH_ENABLED=false
EOF

# 3. Start the server
uvicorn server.main:app --reload --port 8000

# 4. In a second terminal — add a test company
curl -s -X POST http://localhost:8000/api/v1/admin/companies \
  -H "X-Admin-Key: change-me-strong-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"company_id":"demo-corp","company_name":"Demo Corp","enabled":true}'

# 5. Copy and configure agent
cp agent/agent_config.yaml.example agent/agent_config.yaml
# Edit company_id, server_url, and set connector.type: "mock"

# 6. Start the agent (in a third terminal)
python -m agent.agent --config agent/agent_config.yaml
```

Dashboard: `http://localhost:8000`  
Agent dashboard: `http://localhost:7979`

---

## Legacy scripts

`saas_monitor.py` and `saas_monitor_automatic_revoke.py` are older standalone scripts
that connected directly to Frappe + Microsoft/Google APIs. They are superseded by the
`server/` + `agent/` architecture documented in the main README.
