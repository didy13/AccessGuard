# SaaS Access Audit Monitor

    Ovaj projekat sluzi za automatsku detekciju "Access Gap-a", sastoji se od:
    - Frappe backend‑a (sa HRMS aplikacijom) – izvor podataka o zaposlenima.
    - Python monitora (`saas_monitor.py`) koji periodično proverava zaposlene sa statusom `Left` i ispituje Microsoft Graph API za aktivne tokene.
    - Pomoćne skripte (`revoke_users_token.py`) za ručno brisanje svih OAuth grantova za određenog korisnika.

## Docker

    Ceo sistem se oslanja na Docker (Frappe development kontejner) kako bi svi imali identično okruženje.

### Kako pokrenuti docker (host)
    
    1. **Startovanje kontejnera**:
        Otvorite folder u VS Code-u i kada se pojavi prompt, kliknite na "Reopen in Container"
    2. **Pokretanje aplikacije**:
        Unutar terminala:
            cd frappe-bench
            bench start
            bench --site development.localhost ngrok --bind-tls
    
    Sajt ce biti onda dostupan na http://development.localhost:8000

### Kako se povezati (Ngrok)

    Jedan lapotop ce da bude host koji pokrece docker, dok ce ostali biti klijenti koji se povezuju

    1. **Host**:
        Startuje frappe_docker i pokrece ngrok
    2. **Klijenti**:
        U python scripti:
            BASE_RUL: "link koji host prosledjuje"
            Za pristupu bazi host prosledjuje API Key i Secret koji se generisu unutar dockera

## Microsoft Azure

    U projektu koristimo Microsoft Graph API za:
        1. Čitanje OAuth2PermissionGrant aktivnih tokena za korisnike
        2. Brisanje tih grantova kada je potrebno opozvati pristup
        3. Uzimanje ID‑a korisnika na osnovu email adrese.

    Komponente u Azure
        1. Applikacija koju smo napravili preko App registration, nazvali smo ga M365
        2. App M365 dodati API permissions: 'User.Read.All' (app permission), 'DelegatedPermissionGrant.ReadWrite.All' (app permission)
        3. App M365 dodati API permissions: 'offline_access' (Delegated), Mail.Read (Delegated), User.Read (Delegated)

## Scripte

### Podešavanje .env

    U folderu the_smekeri_oauth/ kreirati .env sa sledećim sadržajem:

        # Frappe
        BASE_URL=http://development.localhost:8000   # ili ngrok URL
        API_KEY=vaš_api_kez
        API_SECRET=vaš_secret_api

        # Microsoft Azure
        MICROSOFT_TENANT_ID=vaš_microsoft_tenant_id
        MICROSOFT_CLIENT_ID=vaš_microsoft_client_id
        MICROSOFT_CLIENT_SECRET=vaš_microsoft_client_secret
        MICROSOFT_CLIENT_APP_ID=vaš_microsoft_client_app_id
        MICROSOFT_TENANT_APP_ID=vaš_microsoft_tenant_app_id
        MICROSOFT_SECRET_APP=vaš_microsoft_app_secret_value

### Pokretanje python scripti iz foldera the_smekeri_oauth

    1. Instalirati python 3.x.x
    2. Pokrenuti komandu u folderu: python -m pip install -r requirements.txt
    3. Uslov je da bude pokrenut frappe_bench, pristupiti njemu ili preko localhost:8000 ili ngrok linka koji host prosleđuje

### Kako funkcioniše saas_monitor.py

    Svaki put kad se pokrene:
        1. Povezuje se na Frappe i uzima zaposlene sa statusom  u poslednjih 30 dana
        2. Dobija access tokene za Microsoft Graph
        3. Za svakog zaposlenog poziva GET oauth2PermissionGrants
        4. Ako pronađe grent pravi Access Audit Alert u Frappe-u za tog korisnika

### Kako funkcioniše revoke_users_token.py

    Služi za ručno brisanje grantova određenog korisnika
        1. Skripta će tražiti unos email-a korisnika
        2. Prikazaće pronađene grentove
        3. Na kraju će imati ispis koliko je gratova izbrisala a koliko je neuspešnih pokušaja imala