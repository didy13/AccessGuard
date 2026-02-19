import requests
import sys
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")

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

    fields = json.dumps(["name", "employee_name", "company_email", "relieving_date"])

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
        reponse = requests.post(url, headers=frappe_headers, json=data)

        if reponse.status_code == 200:
            print(f"Alert created for {employee_name} - {saas_app}")
            return response.json()
        else:
            print(f"Error creating alert: {reponse.text}")
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

        ms_grants = check_microsoft_oauth_grants(email, ms_token)
        if ms_grants is None:
            print("Provera nije uspela (moguć problem sa pristupom).")
            continue

        if ms_grants:
            create_access_audit_allert(name, email, "M365", "High")
        else:
            print(f"Nema aktivnih Microsoft tokena.")

if __name__ == "__main__":
    main()