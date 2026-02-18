import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime
from google.oauth2 import service_account
import google.auth.transport.requests

load_dotenv()

BASE_URL = os.getenv("FRAPPE_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

if not API_KEY or not API_SECRET:
    print("API_KEY and API_SECRET must be set in the .env file")
    exit()

frappe_headers = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
}

def get_employees_who_left():
    filters = json.dumps([["Employee", "status", "=", "Left"]])

    fields = json.dumps(["name", "employee_name", "company_email", "status"])

    url = f"{BASE_URL}/api/resource/Employee?filters={filters}&fields={fields}"

    response = requests.get(url, headers=frappe_headers)

    if response.status_code == 200:
        return response.json().get("data", [])
    else:
        print(f"Greska: {response.text}")
        return []
    


# --- Frappe part ---
def get_frappe_logged_user(base_url, token):
    url = f"{base_url}/api/method/frappe.auth.get_logged_user"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()["message"]

# --- Microsoft part ---
def get_microsoft_graph_token():
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        raise ValueError("Missing Microsoft credentials. Please set TENANT_ID, CLIENT_ID, and CLIENT_SECRET in your .env file.")

    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET, # Secret is read from env, not hardcoded
        "scope": "https://graph.microsoft.com/.default"
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]

def get_microsoft_graph_tokens(user_email, access_token):
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/oauth2PermissionGrants"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("value", [])
    return []


def get_google_admin_token(service_account_file, impersonate_email, scopes):
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=scopes,
        subject=impersonate_email
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token

def get_google_tokens(user_email, access_token):
    url = f"https://admin.googleapis.com/admin/directory/v1/users/{user_email}/tokens"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("items", [])
    return []

# --- Main execution ---
if __name__ == "__main__":
    # Frappe credentials
    frappe_base = "https://your-frappe.com"
    frappe_token = "your-frappe-bearer-token"

    # Microsoft Azure AD credentials
    ms_tenant = "your-tenant-id"
    ms_client_id = "your-client-id"
    ms_client_secret = "your-client-secret"

    # Google service account
    google_sa_file = "path/to/service-account.json"
    google_admin_email = "admin@yourdomain.com"  # An admin with directory read privileges
    google_scopes = ["https://www.googleapis.com/auth/admin.directory.user.security"]

    # Get logged-in user from Frappe
    user = get_frappe_logged_user(frappe_base, frappe_token)
    print(f"Logged-in user: {user}")

    # Microsoft tokens
    ms_token = get_microsoft_graph_token(ms_tenant, ms_client_id, ms_client_secret)
    ms_grants = get_microsoft_graph_tokens(user, ms_token)
    print("Microsoft grants:", ms_grants)

    # Google tokens
    google_token = get_google_admin_token(google_sa_file, google_admin_email, google_scopes)
    google_items = get_google_tokens(user, google_token)
    print("Google tokens:", google_items)

def create_access_audit_allert(employee_name, email, saas_app, risk="High"):
    url = f"{BASE_URL}/api/resource/Access Audit Alert List"
    data = {
        "employee_name": employee_name,
        "email": email,
        "saas_app": saas_app,
        "risk": risk,
        "detection_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        reponse = requests.post(url, headers=frappe_headers, json=data)

        if reponse.status_code == 200:
            print(f"Alert created for {employee_name} - {saas_app}")
            return response.json()
        else:
            print(f"Error creating alert: {reponse.text}")
        
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

leavers = get_employees_who_left()
for person in leavers:
    print(f"{person['employee_name']} ({person['company_email']}) - Status: {person['status']}")
    email = person.get("company_email") 
    name = person.get("employee_name")

    ms_gaps = get_microsoft_graph_tokens(email, ms_token)
    if ms_gaps:
        create_access_audit_allert(name, email, "M365", "High")
    
    google_tokens = get_google_tokens(email, google_token)
    if google_tokens:
        create_access_audit_allert(name, email, "Google", "High")