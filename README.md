# SaaS Access Audit Monitor

    Ovaj projekat sluzi za automatsku detekciju "Access Gap-a", sastoji se od:
    - Frappe backend‑a (sa HRMS aplikacijom) – izvor podataka o zaposlenima.
    - Python monitora (`saas_monitor.py`) koji periodično proverava zaposlene sa statusom `Left` i ispituje Microsoft Graph API za aktivne tokene.
    - Pomoćne skripte (`revoke_users_token.py`) za ručno brisanje svih OAuth grantova za određenog korisnika.

## Docker

    Ceo sistem se oslanja na Docker (Frappe development kontejner) kako bi svi imali identično okruženje.

### Kako pokrenuti docker (host)
    
    1. Startovanje kontejnera:
        Otvorite folder u VS Code-u i kada se pojavi prompt, kliknite na "Reopen in Container"
    2. Pokretanje aplikacije:
        Unutar terminala:
            cd frappe-bench
            bench start
            bench --site development.localhost ngrok --bind-tls
    
    Sajt ce biti onda dostupan na http://development.localhost:8000

### Kako se povezati (Ngrok)

    Jedan lapotop ce da bude host koji pokrece docker, dok ce ostali biti klijenti koji se povezuju

    - Host:
        Startuje frappe_docker i pokrece ngrok
    - Klijenti:
        U python scripti:
            BASE_RUL: "link koji host prosledjuje"
            Za pristupu bazi host prosledjuje API Key i Secret koji se generisu unutar dockera

## Microsoft Azure

    U projektu koristimo Microsoft Graph API za:
    
        1. Čitanje OAuth2PermissionGrant aktivnih tokena za korisnike
        2. Brisanje tih grantova kada je potrebno opozvati pristup
        3. Opozivanje svih sesija za korisnika
        4. Uzimanje ID‑a korisnika na osnovu email adrese.

    ### Komponente u Azure
    
        1. Applikacija koju smo napravili preko App registration, nazvali smo je M365
        2. API Permissions dodate aplikaciji:
            - Application permissions
                * `User.Read.All`
                * `DelegatedPermissionGrant.ReadWrite.All`
                * `User.Read`
            - Delegated permissions
                * `offline_access`
                * `Mail.Read`
                * `User.Read`
        3. Client credentials:
            - Kreiran Client Secret (vrednost sačuvana u `.env` fajlu)
            - Zabeležen Client ID (Application ID)
            - Zabeležen Tenant ID (Directory ID)

    ### Azure API endpointi koje koristimo:

         1. Dobijanje access tokena: POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
         2. Čitanje OAuth grantova za korisnika: GET https://graph.microsoft.com/v1.0/users/{email}/oauth2PermissionGrants
         3. Brisanje OAuth granta: DELETE https://graph.microsoft.com/v1.0/oauth2PermissionGrants/{grant_id}
         4. Opozivanje svih sesija korisnika: POST https://graph.microsoft.com/v1.0/users/{email}/revokeSignInSessions

## Google Workspace

    U projektu koristimo Google Admin SDK API za:
    
        1. Čitanje aktivnih OAuth tokena za korisnike (`tokens().list()`)
        2. Brisanje tih tokena kada je potrebno opozvati pristup (`tokens().delete()`)

    ### Komponente u Google Cloud Console-u:
    
        1. Projekat u Google Cloud Console-u (npr. `saas-monitor`)
        2. Service account sa domain-wide delegation (DWD) podešavanjem
        3. API scopes (OAuth 2.0 opsezi) koje smo dodali u Google Admin konzoli

    ### Potrebni API-ji i scope-ovi:

        - Admin SDK API – obavezan za Directory API (tokens.list, tokens.delete)
        - Reports API – opciono, ali koristi se u funkciji `get_active_tokens_for_user()` za audit logove
        - `https://www.googleapis.com/auth/admin.directory.user.readonly` – čitanje osnovnih podataka o korisnicima
        - `https://www.googleapis.com/auth/admin.directory.user.security` – ključan za pristup tokenima (list i delete)

    ### Google API endpointi koje koristimo:

        1. Listanje tokena za korisnika: GET https://admin.googleapis.com/admin/directory/v1/users/{userKey}/tokens
        2. Brisanje tokena za korisnika i klijenta: DELETE https://admin.googleapis.com/admin/directory/v1/users/{userKey}/tokens/{clientId}
        3. Čitanje audit logova tokena: GET https://admin.googleapis.com/admin/reports/v1/activity/users/all/applications/token

## Scripte

### Podešavanje .env

    U folderu the_smekeri_oauth/ kreirati .env sa sledećim sadržajem:

        BASE_URL=http://development.localhost:8000/ ili link koji host prosledi
        API_KEY=
        API_SECRET=
        
        MICROSOFT_TENANT_ID=
        MICROSOFT_CLIENT_ID=
        MICROSOFT_CLIENT_SECRET=
        MICROSOFT_CLIENT_APP_ID=
        MICROSOFT_TENANT_APP_ID=
        MICROSOFT_SECRET_APP=
        
        SERVICE_ACCOUNT_FILE='google.json'
        ADMIN_EMAIL=
        GOOGLE_CLIENT_OAUTH2_ID=
        GOOGLE_CLIENT_OAUTH2_SECRET=

### Pokretanje python scripti iz foldera the_smekeri_oauth

    1. Instalirati python 3.x.x
    2. Pokrenuti komandu u folderu: python -m pip install -r requirements.txt
    3. Uslov je da bude pokrenut frappe_bench, pristupiti njemu ili preko localhost:8000 ili ngrok linka koji host prosleđuje

### Kako funkcioniše saas_monitor.py

    Svaki put kad se pokrene:
        1. Povezuje se na Frappe i uzima zaposlene sa statusom Left u poslednjih 30 dana
        2. Dobija access tokene za Microsoft Graph (OAuth 2.0 client credentials flow)
        3. Za svakog zaposlenog:
            - Poziva Microsoft Graph API `/users/{email}/oauth2PermissionGrants` da proveri aktivne OAuth tokene
            - Ako pronađe grantove, kreira Access Audit Alert u Frappe-u za tog korisnika
        4. Za zaposlene sa domenom `@thesmekeri.biz` dodatno proverava:
            - Google Workspace tokene koristeći Google Admin SDK Directory API
            - Koristi service account sa domain-wide delegacijom za pristup Google tokenima
            - Poziva `tokens().list()` za svakog korisnika da dobije listu aktivnih OAuth tokena
            - Ako pronađe Google tokene, kreira Access Audit Alert sa detaljima (naziv aplikacije, client ID)
        5. Za svaki pronađeni token (Microsoft ili Google) kreira se jedinstveni alert koji sadrži:
            - Ime zaposlenog
            - Email adresu
            - SaaS aplikaciju (M365 ili Google Workspace) sa brojem tokena
            - Status (Open)
            - Rizik (Low/Medium/High na osnovu radnog mesta)
            - Detaljan opis sa listom aplikacija i brojem tokena po aplikaciji
        6. Automatski se pokreće na svakih 15 minuta (pomoću `schedule` biblioteke)

### Kako funkcioniše saas_monitor_automatic_revoke.py
    
    Ovaj skript radi slično kao `saas_monitor.py`, ali automatski opoziva pronađene tokene i sesije:

    Svaki put kad se pokrene:
        1. Povezuje se na Frappe i uzima zaposlene sa statusom Left u poslednjih 30 dana
        2. Dobija access tokene za Microsoft Graph (OAuth 2.0 client credentials flow)
        3. Za svakog zaposlenog:
            - Poziva Microsoft Graph API `/users/{email}/oauth2PermissionGrants` da proveri aktivne OAuth tokene
            - Ako pronađe grantove:
                * Opoziva sve sesije (`/revokeSignInSessions`)
                * Briše sve OAuth grantove (`/oauth2PermissionGrants/{id}`)
                * Kreira Access Audit Alert u Frappe-u sa statusom Closed ako su obe operacije uspele
                * Ako neka operacija nije uspela, alert dobija status Open
        4. Za zaposlene sa domenom `@thesmekeri.biz` dodatno proverava:
            - Google Workspace tokene koristeći Google Admin SDK Directory API
            - Poziva `tokens().list()` za svakog korisnika
            - Ako pronađe tokene:
                * Briše svaki token pojedinačno (`tokens().delete()`)
                * Kreira Access Audit Alert sa statusom Closed ako je brisanje uspelo
                * Ako brisanje nije uspelo, alert dobija status Open
        5. Za svaki pronađeni token (Microsoft ili Google) kreira se jedinstveni alert koji sadrži:
            - Ime zaposlenog
            - Email adresu
            - SaaS aplikaciju (M365 ili Google Workspace) sa brojem tokena
            - Status (Closed ako su svi tokeni uspešno obrisani, inače Open)
            - Rizik (Low/Medium/High na osnovu radnog mesta)
            - Detaljan opis sa listom aplikacija i brojem tokena po aplikaciji
        6. Automatski se pokreće na svakih 15 minuta (pomoću `schedule` biblioteke)

### Kako staviti tokene preko powershell

    Microsoft:
        1. Install-Module Microsoft.Graph.Authentication -Scope CurrentUser -Force
        2. Import-Module Microsoft.Graph.Authentication
        3. Posle toga porkenuti u drugom powershell-u sve sto je sacuvano u powershell-runAzure.txt
        **Napomena** ukoliko ne prihvata komande pokrenuti powershell kao administrator
