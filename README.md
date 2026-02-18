# SaaS Access Audit Monitor

Ovaj projekat sluzi za automatsku detekciju "Access Gap-a"

# Docker

Ovaj repositorijum koristi **Docker** kao bazu za nas SaaS Monitor, on nam omogucava da imamo identicno
serversko okruzenje

## Kako pokrenuti

    1. Instalirati **Docker Desktop**  i **VS Code**
    2. Instalirati VS Code ekstenziju 'Dev Containers'
    3. Otvorite ovaj folder u VS Code-u
    4. Kliknite "Reopen in Container"
    5. Sacekajte da se otvori i u tom trenutku vas server ce biti spreman na portu '8000'

## Pokretanje saas_monitor.py
    1. Instalirati python 3.x.x
    2. Pokrenuti komandu u folderu: python -m pip install -r requirements.txt
    3. Uslov je da bude pokrenut frappe_bench, pristupiti njemu ili preko localhost:8000 ili ngrok linka koji host prosleđuje

## Arhitektura sistema
Nas sistem se sastoji od nekoliko kontejnera koji rade zajedno:
    1. **frape-bench**: Glavni kontejner gde se nalazi nas Python kod (Frappe framework)
    2. **mariadb**: Baza podataka gde se cuvaju zaposleni i nas alarm
    3. **redis**: Sluzi za kesiranje i brze procese

## Kako pokrenuti docker (host)
    
    1. **Startovanje kontejnera**:
        Otvorite folder u VS Code-u i kada se pojavi prompt, kliknite na "Reopen in Container"
    2. **Pokretanje aplikacije**:
        Unutar terminala:
            cd frappe-bench
            bench start
    
    Sajt ce biti onda dostupan na http://development.localhost:8000

## Kako se povezati (Ngrok)
Jedan lapotop ce da bude host koji pokrece docker, dok ce ostali biti klijenti koji se povezuju

    1. **Host**:
        Preko ngrok htto 8000 dobijam link sa interneta preko koga ce klijenti da se povezu
    2. **Klijenti**:
        U python scripti:
            BASE_RUL: "link koji host prosledjuje"
            Za pristupu bazi host prosledjuje API Key i Secret koji se generisu unutar dockera
