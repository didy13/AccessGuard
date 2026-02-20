import requests
import sys
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# Frappe
BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# Azure
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")

#Google
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user.readonly',
    'https://www.googleapis.com/auth/admin.reports.audit.readonly'
]
ADMIN_EMAIL = os.getenv("GOOGLE_ADMIN_EMAIL")

if not API_KEY or not API_SECRET:
    print("API_KEY and API_SECRET must be set in the .env file")
    exit()

frappe_headers = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def get_employees_who_left(days_back = 30):
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    filters = json.dumps([
        ["status", "=", "Left"],
        ["relieving_date", ">=", from_date]
    ])

    fields = json.dumps(["name", "employee_name", "company_email", "relieving_date", "status"])

    url = f"{BASE_URL}/api/resource/Employee?filters={filters}&fields={fields}"

    response = requests.get(url, headers=frappe_headers)

    if response.status_code == 200:
        return response.json().get("data", [])
    else:
        print(f"Greska: {response.text}")
        return []

def get_microsoft_access_token(MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET):
    url = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": MICROSOFT_CLIENT_ID,
        "client_secret": MICROSOFT_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }
    try:
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
        token = response.json()["access_token"]
        print("Microsoft access token uspešno dobijen.")
        return token
    except requests.exceptions.RequestException as e:
        print(f"Greška pri dobijanju Microsoft tokena: {e}")
        return None

def create_access_audit_allert(employee_name, email, saas_app, risk="High"):
    url = f"{BASE_URL}/api/resource/Access Audit Alert"
    data = {
        "employee_name": employee_name,
        "email": email,
        "saas_app": saas_app,
        "risk": risk,
        "detection_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        response = requests.post(url, headers=frappe_headers, json=data)

        if response.status_code == 200:
            print(f"Alert created for {employee_name} - {saas_app}")
            return response.json()
        else:
            print(f"Error creating alert: {response.text}")
            return None
        
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return None

def check_microsoft_oauth_grants(user_email, access_token):
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/oauth2PermissionGrants"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            grants = response.json().get("value", [])
            return grants
        else:
            print(f"Microsoft API greška za {user_email}: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Izuzetak pri proveri Microsoft tokena za {user_email}: {e}")
        return None

def get_active_tokens_for_user(user_email):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        
        delegated_credentials = credentials.with_subject(ADMIN_EMAIL)

        service = build('admin', 'reports_v1', credentials=delegated_credentials)

        results = service.activities().list(
            userKey=user_email,
            applicationName='token',
            maxResults=100
        ).execute()

        activities = results.get('items', [])
        
        active_tokens_for_user = []
        for activity in activities:
            actor_email = activity.get('actor', {}).get('email')
            if actor_email == user_email:
                for event in activity.get('events', []):
                    if event.get('type') == 'authorize' or event.get('name') == 'token_authorize':
                        for param in event.get('parameters', []):
                            if param.get('name') == 'application_name':
                                app_name = param.get('value')
                                active_tokens_for_user.append({
                                    'application': app_name,
                                    'timestamp': activity.get('id', {}).get('time')
                                })
        return active_tokens_for_user

    except HttpError as err:
        print(f"API Greška: {err}")
        return None
    except Exception as e:
        print(f"Opšta greška: {e}")
        return None

def main():
    leavers = get_employees_who_left(days_back=30)
    if not leavers:
        print("Nema zaposlenih za proveru.")
        return
    
    ms_token = get_microsoft_access_token(MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET)
    if not ms_token:
        print("Ne mogu da nastavim bez Microsoft tokena.")
        exit()

    for person in leavers:
        print(f"{person['employee_name']} ({person['company_email']}) - Status: {person['status']}")
        email = person.get("company_email") 
        name = person.get("employee_name")

        if not email:
            continue

        # Microsoft provera
        ms_grants = check_microsoft_oauth_grants(email, ms_token)
        if ms_grants is None:
            print("Provera nije uspela (moguć problem sa pristupom).")
        else:
            if ms_grants:
                create_access_audit_allert(name, email, "M365", "High")
            else:
                print(f"Nema aktivnih Microsoft tokena.")

        # Google provera
        email_domen = email.split('@')[1]
        if email_domen == "thesmekeri.biz":
            google_tokens = get_active_tokens_for_user(email)
            if google_tokens is None:
                print(f"Došlo je do greške pri komunikaciji sa Google API-jem za {email}.")
            elif not google_tokens:
                print(f"Korisnik {email} nema aktivnih OAuth tokena (prema istoriji).")
            else:
                print(f"Korisnik {email} ima aktivne tokene za {len(google_tokens)} aplikacija:")
                for t in google_tokens:
                    print(f"- {t['application']} (od: {t['timestamp']})")
                    create_access_audit_allert(name, email, f"Google:{t['application']}", "High")

if __name__ == "__main__":
    main()
