#!/bin/bash
set -e
export UV_LINK_MODE=copy

echo "🔄 Čekam da MariaDB bude spreman..."
until mysqladmin ping -h mariadb -u root -p123 --silent; do
    echo "⏳ Čekam MariaDB..."
    sleep 2
done
echo "✅ MariaDB je spreman!"

# Podesi pyenv za frappe korisnika
export PYENV_ROOT="/home/frappe/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

echo "🔄 Instaliram Python 3.11.9 (ako već nije)..."
pyenv install 3.11.9 -s
pyenv shell 3.11.9
echo "🐍 Python verzija: $(python --version)"

cd /workspace/development

# Preuzmi installer.py ako ne postoji
if [ ! -f "installer.py" ]; then
    echo "📥 Preuzimam installer.py iz Frappe Docker repozitorijuma..."
    curl -o installer.py https://raw.githubusercontent.com/frappe/frappe_docker/develop/development/installer.py
fi

if [ ! -d "frappe-bench" ]; then
    echo "🛠️ Pokrećem Frappe installer..."
    python3 installer.py

    echo "🔧 Popravljam MySQL privilegije za sajt..."
    cd /workspace/development/frappe-bench

    # Sačekaj da site_config.json bude kreiran
    timeout=10
    while [ ! -f sites/development.localhost/site_config.json ] && [ $timeout -gt 0 ]; do
        sleep 1
        timeout=$((timeout-1))
    done

    if [ ! -f sites/development.localhost/site_config.json ]; then
        echo "❌ site_config.json nije pronađen! Proveri da li je sajt kreiran."
        exit 1
    fi

    # Izdvoj podatke iz JSON-a
    DB_NAME=$(python3 -c "import sys, json; f=open('sites/development.localhost/site_config.json'); data=json.load(f); f.close(); print(data['db_name'])")
    DB_USER=$DB_NAME
    DB_PASSWORD=$(python3 -c "import sys, json; f=open('sites/development.localhost/site_config.json'); data=json.load(f); f.close(); print(data['db_password'])")

    echo "   DB_NAME: $DB_NAME"
    echo "   DB_USER: $DB_USER"

    # Dodeli privilegije sa bilo kog hosta
    mysql -h mariadb -u root -p123 -e "GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}'; FLUSH PRIVILEGES;"

    # Proveri da li je GRANT uspeo
    echo "🔍 Proveravam pristup za korisnika $DB_USER..."
    if mysql -h mariadb -u "$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1" &>/dev/null; then
        echo "✅ Povezivanje uspešno – privilegije su ispravne."
    else
        echo "❌ Ne mogu da se povežem kao $DB_USER. Proveri GRANT komandu."
        exit 1
    fi

    echo "📦 Instaliram HRMS aplikaciju..."
    bench get-app hrms --branch version-15
    bench --site development.localhost install-app hrms
    bench --site development.localhost set-config developer_mode 1
else
    echo "✅ Bench već postoji, preskačem inicijalizaciju."
    cd /workspace/development/frappe-bench
fi

# Podesi permisije za log fajl
touch logs/bench.log 2>/dev/null || true
chmod 666 logs/bench.log 2>/dev/null || true

# Instaliraj Python pakete za SaaS monitor (ako postoji requirements.txt)
if [ -f "/workspace/requirements.txt" ]; then
    echo "📦 Instaliram SaaS monitor dependencies..."
    pip install -r /workspace/requirements.txt
else
    echo "⚠️ requirements.txt nije pronađen, preskačem."
fi

# Podesi cron za SaaS monitor (opciono)
echo "⏰ Podešavam cron za SaaS monitor..."
(crontab -l 2>/dev/null || echo "") | grep -v "saas_monitor.py" | { cat; echo "*/15 * * * * cd /workspace && /usr/local/bin/python saas_monitor.py >> /workspace/saas_monitor.log 2>&1"; } | crontab - 2>/dev/null || echo "⚠️ Cron podešavanje nije uspelo (nije problem)."

echo ""
echo "🎉 ===== SVE JE SPREMNO! ====="
echo "▶️ Sada možeš pokrenuti: cd /workspace/development/frappe-bench && bench start"
echo "🌐 Frappe je dostupan na: http://localhost:8000"
echo "🔑 Login: Administrator / admin"