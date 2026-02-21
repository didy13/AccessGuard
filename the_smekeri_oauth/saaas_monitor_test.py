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
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user.readonly',
    'https://www.googleapis.com/auth/admin.reports.audit.readonly'
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

def create_consolidated_alert(employee_name, email, saas_app, token_count, token_details=None, risk="High"):
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

def get_active_tokens_for_user(user_email):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        delegated_credentials = credentials.with_subject(ADMIN_EMAIL)

        service = build('admin', 'reports_v1', credentials=delegated_credentials)

        results = service.activities().list(
            userKey='all',
            applicationName='token',
            maxResults=500
        ).execute()

        activities = results.get('items', [])
        
        active_tokens_for_user = []
        for activity in activities:
            actor_email = activity.get('actor', {}).get('email', '')
            if actor_email.lower() == user_email.lower():
                
                for event in activity.get('events', []):
                    event_type = event.get('type', '').lower()
                    event_name = event.get('name', '').lower()
                    
                    token_keywords = ['authorize', 'token', 'oauth', 'grant', 'consent', 'issue']
                    
                    is_token_event = any(
                        keyword in event_type or keyword in event_name 
                        for keyword in token_keywords
                    )
                    
                    if is_token_event:
                        token_info = {
                            'application': 'Unknown App',
                            'timestamp': activity.get('id', {}).get('time'),
                            'client_id': None,
                            'scopes': []
                        }

                        for param in event.get('parameters', []):
                            param_name = param.get('name')
                            param_value = param.get('value', '')
                            
                            if param_name == 'application_name':
                                token_info['application'] = param_value
                            elif param_name == 'client_id':
                                token_info['client_id'] = param_value
                                if token_info['application'] == 'Unknown App' and param_value:
                                    known_app = get_application_name_from_client_id(param_value)
                                    if known_app:
                                        token_info['application'] = known_app
                                    else:
                                        token_info['application'] = f'Client: {param_value[:8]}...'
                            elif param_name == 'scope':
                                token_info['scopes'] = param_value.split() if param_value else []
                            elif param_name == 'app_name':
                                token_info['application'] = param_value
                            elif param_name == 'service_name':
                                if token_info['application'] == 'Unknown App':
                                    token_info['application'] = param_value
                            elif param_name == 'oauth_client_name':
                                token_info['application'] = param_value

                        if token_info['application'] == 'Unknown App' and token_info['scopes']:
                            scopes_str = ' '.join(token_info['scopes'])
                            if 'playground' in scopes_str.lower():
                                token_info['application'] = 'Google OAuth Playground'
                        
                        active_tokens_for_user.append(token_info)
        
        return active_tokens_for_user

    except HttpError as err:
        print(f"Google API Greška za {user_email}: {err}")
        if err.resp.status == 403:
            print("Verovatno domain-wide delegation nije ispravno podešen!")
        return None
    except Exception as e:
        print(f"Opšta greška za {user_email}: {e}")
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
                    risk="High"
                )
            else:
                print(f"Nema aktivnih Microsoft tokena.")

        # Google provera
        if email.endswith('@thesmekeri.biz'):
            google_tokens = get_active_tokens_for_user(email)
            
            if google_tokens is None:
                print(f"Došlo je do greške pri komunikaciji sa Google API-jem.")
            elif not google_tokens:
                print(f"Nema aktivnih Google OAuth tokena.")
            else:
                google_count = len(google_tokens)
                print(f"Pronađeno {google_count} aktivnih Google tokena!")
                
                create_consolidated_alert(
                    employee_name=name,
                    email=email,
                    saas_app="Google Workspace",
                    token_count=google_count,
                    token_details=google_tokens,
                    risk="High"
                )

if __name__ == "__main__":
    main()