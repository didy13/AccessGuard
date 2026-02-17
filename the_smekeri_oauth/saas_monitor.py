import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

BASE_URL = os.getenv("FRAPPE_URL")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

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
    
def get_microsoft_graph_tokens(user_email, access_token):
    url_mc = f"https://graph.microsoft.com/v1.0/users/{user_email}/outh2PermissionGrants"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url_mc, headers=headers)
    
    if response.status_code == 200:
        grants = response.json().get("value", [])
        if grants:
            return grants
    return []

def get_google_tokens(user_email, access_token):
    url_google = f"https://admin.googleapis.com/admin/directory/v1/users/{user_email}/tokens"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url_google, headers=headers)

    if response.status_code == 200:
        return response.json().get("items", [])
    return [] 

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