import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

MICROSOFT_TENANT_APP_ID = os.getenv("MICROSOFT_TENANT_APP_ID")
MICROSOFT_CLIENT_APP_ID = os.getenv("MICROSOFT_CLIENT_APP_ID")
MICROSOFT_SECRET_APP = os.getenv("MICROSOFT_SECRET_APP")

def get_access_token():
    url = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_APP_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": MICROSOFT_CLIENT_APP_ID,
        "client_secret": MICROSOFT_SECRET_APP,
        "scope": "https://graph.microsoft.com/.default"
    }
    try:
        resp = requests.post(url, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:
        print(f"Greška pri dobijanju tokena: {e}")
        return None

def get_user_id(email, token):
    url = f"https://graph.microsoft.com/v1.0/users/{email}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()["id"]
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 404:
            print(f"Korisnik {email} ne postoji u Azure AD.")
        else:
            print(f"Greška pri dohvatanju korisnika: {resp.text}")
        return None
    except Exception as e:
        print(f"Greška: {e}")
        return None
    
def list_grants_for_user(user_id, token):
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/oauth2PermissionGrants"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception as e:
        print(f"Greška pri listanju grantova: {e}")
        return []
    
def delete_grant(grant_id, token):
    url = f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants/{grant_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.delete(url, headers=headers, timeout=30)
        if resp.status_code == 204:
            print(f"Grant {grant_id} obrisan.")
            return True
        else:
            print(f"Greška pri brisanju granta {grant_id}: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"Greška pri brisanju: {e}")
        return False
    
def main():
    TARGET_EMAIL = input("Unesi email korisnika:").strip()
    if not TARGET_EMAIL:
        print("Nisi uneo email. Prekidam.")
        sys.exit(1)

    print(f"Opozi sve tokene za: {TARGET_EMAIL}")

    token = get_access_token()
    if not token:
        sys.exit(1)

    user_id = get_user_id(TARGET_EMAIL, token)
    if not user_id:
        sys.exit(1)

    grants = list_grants_for_user(user_id, token)
    if not grants:
        print("Nema nijednog granta za ovog korisnika.")
        return
    
    print(f"\nPronađeno {len(grants)} grantova:")

    for g in grants:
        print(f"   - ID: {g.get('id')} | Client: {g.get('clientId')} | Scope: {g.get('scope')}")
    
    uspesno = 0
    neuspesno = 0
    for g in grants:
        if delete_grant(g["id"], token):
            uspesno += 1
        else:
            neuspesno += 1

    print(f"\nObrisano: {uspesno}, neuspešno: {neuspesno}")
    if neuspesno == 0:
        print("Sada pokreni svoj saas_monitor - trebalo bi da ne vidi više tokene za ovog korisnika.")
    else:
        print("Neki grantovi nisu obrisani. Proveri dozvole aplikacije.")

if __name__ == "__main__":
    main()