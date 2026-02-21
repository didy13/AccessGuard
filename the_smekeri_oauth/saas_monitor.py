import requests
import sys
import json
import os
import schedule
import time
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
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user.readonly',
    'https://www.googleapis.com/auth/admin.directory.user.security'
]
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

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

    fields = json.dumps(["name", "employee_name", "company_email", "relieving_date", "status", "designation"])

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

def create_consolidated_alert(employee_name, email, saas_app, token_count, status, risk, token_details=None):
    url = f"{BASE_URL}/api/resource/Access Audit Alert"
    
    description = ""
    if token_details and len(token_details) > 0:
        app_counts = {}
        for token in token_details:
            app = token.get('application', 'Nepoznata aplikacija')
            app_counts[app] = app_counts.get(app, 0) + 1
        
        description = f"Pronađeno {token_count} aktivnih tokena:\n"
        for app, count in sorted(app_counts.items(), key=lambda x: x[1], reverse=True)[:10]:  # Prvih 10 aplikacija
            description += f"  • {app}: {count} tokena\n"
        
        if len(app_counts) > 10:
            description += f"  • ... i još {len(app_counts) - 10} aplikacija\n"

        timestamps = [t.get('timestamp') for t in token_details if t.get('timestamp')]
        if timestamps:
            latest = max(timestamps)
            description += f"\nNajnoviji token: {latest}"
    else:
        description = f"Pronađeno {token_count} aktivnih OAuth tokena za {saas_app}"
    
    data = {
        "employee_name": employee_name,
        "email": email,
        "saas_app": f"{saas_app} ({token_count} tokena)",
        status: status,
        "risk": risk,
        "detection_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "description": description
    }

    try:
        response = requests.post(url, headers=frappe_headers, json=data)

        if response.status_code == 200:
            print(f"Alert created for {employee_name} - {saas_app} ({token_count} tokena)")
            return response.json()
        else:
            print(f"Error creating alert: {response.text}")
            return None
        
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return None

def get_application_name_from_client_id(client_id):
    popular_apps = {
        '407408718192.apps.googleusercontent.com': 'Google OAuth Playground',
        '105463346172544199422': 'saas_monitor',
        '77185425430-npn6h6q1h5k5j5k5j5k5j5k5j5k5j5k5.apps.googleusercontent.com': 'Google Chrome',
        '618104702990-3v5k5j5k5j5k5j5k5j5k5j5k5j5k5j5.apps.googleusercontent.com': 'Google Cloud Shell',
        '32555940559-3v5k5j5k5j5k5j5k5j5k5j5k5j5k5j5.apps.googleusercontent.com': 'Google Cloud SDK',
        '107000923456-3v5k5j5k5j5k5j5k5j5k5j5k5j5k5j5.apps.googleusercontent.com': 'Android device',
    }
    return popular_apps.get(client_id, None)

def list_google_tokens(user_email):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        delegated_credentials = credentials.with_subject(ADMIN_EMAIL)
        service = build('admin', 'directory_v1', credentials=delegated_credentials)

        results = service.tokens().list(userKey=user_email).execute()
        tokens = results.get('items', [])
        return tokens
    except HttpError as err:
        print(f"Google API greška pri listanju tokena za {user_email}: {err}")
        if err.resp.status == 403:
            print("Proverite domain-wide delegation i opsege.")
        return None
    except Exception as e:
        print(f"Opšta greška pri listanju tokena za {user_email}: {e}")
        return None

def get_risk_by_designation(designation):
    if not designation:
        return "Medium"
    if designation.lower() in ['accountant', 'administrative assistant']:
        return "Medium"
    elif designation.lower() in ['business analyst', 'chief executive officer', 'finance manager']:
        return "High"
    elif designation.lower() in ['secretary', 'consultant']:
        return "Low"
    else:
        return "Medium"

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
        ms_tokens = check_microsoft_oauth_grants(email, ms_token)
        if ms_tokens is None:
            print(" Provera nije uspela (moguć problem sa pristupom).")
        else:
            ms_count = len(ms_tokens) if ms_tokens else 0
            if ms_count > 0:
                print(f"Pronađeno {ms_count} aktivnih Microsoft tokena!")
                ms_details = []
                for grant in ms_tokens:
                    ms_details.append({
                        'application': f"Client: {grant.get('clientId', 'Unknown')[:8]}...",
                        'timestamp': datetime.now().isoformat()
                    })

                create_consolidated_alert(
                    employee_name=name,
                    email=email,
                    saas_app="M365",
                    token_count=ms_count,
                    token_details=ms_details,
                    status="Open",
                    risk=get_risk_by_designation(person.get("designation"))
                )
            else:
                print(f"Nema aktivnih Microsoft tokena.")

        # Google provera
        if email.endswith('@thesmekeri.biz'):
            google_tokens = list_google_tokens(email)   # <-- izmenjeno
            if google_tokens is None:
                print("Google provera nije uspela.")
            elif not google_tokens:
                print("Nema aktivnih Google tokena.")
            else:
                google_count = len(google_tokens)
                print(f"Pronađeno {google_count} aktivnih Google tokena!")
                
                # Pripremi detalje za alert (slično kao za Microsoft)
                google_details = []
                for token in google_tokens:
                    app = token.get('displayText', 'Unknown App')
                    client_id = token.get('clientId', '')
                    if not app and client_id:
                        app = f"Client: {client_id[:8]}..."
                    google_details.append({
                        'application': app,
                        'timestamp': datetime.now().isoformat()
                    })
                
                create_consolidated_alert(
                    employee_name=name,
                    email=email,
                    saas_app="Google Workspace",
                    token_count=google_count,
                    token_details=google_details,
                    status="Open",
                    risk=get_risk_by_designation(designation)
                )

schedule.every(15).minutes.do(main)

if __name__ == "__main__":
    main()
    while True:
        schedule.run_pending()
        time.sleep(1)
