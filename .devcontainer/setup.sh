#!/bin/bash
set -e
export UV_LINK_MODE=copy

echo "🔄 Čekam da MariaDB bude spreman..."
until mysqladmin ping -h mariadb -u root -p123 --silent; do
    echo "⏳ Čekam MariaDB..."
    sleep 2
done
echo "✅ MariaDB je spreman!"

export PYENV_ROOT="/home/frappe/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

echo "🔄 Instaliram Python 3.11.9 (ako već nije)..."
pyenv install 3.11.9 -s
pyenv shell 3.11.9
echo "🐍 Python verzija: $(python --version)"

echo "🔧 Popravljam vlasništvo nad /workspace/development..."
sudo chown -R frappe:frappe /workspace/development 2>/dev/null || echo "⚠️ Nisam mogao da promenim vlasništvo, ali nastavljam..."

cd /workspace/development

# Potpuno čišćenje pre početka
if [ -d "frappe-bench" ]; then
    echo "⚠️ Brišem stari frappe-bench direktorijum..."
    rm -rf frappe-bench
fi
if [ -d "apps" ]; then
    echo "⚠️ Brišem stari apps direktorijum..."
    rm -rf apps
fi

# Preuzmi installer.py ako ne postoji
if [ ! -f "installer.py" ]; then
    echo "📥 Preuzimam installer.py iz Frappe Docker repozitorijuma..."
    curl -f -o installer.py https://raw.githubusercontent.com/frappe/frappe_docker/develop/development/installer.py
    if [ $? -ne 0 ] || [ ! -s "installer.py" ]; then
        echo "❌ Neuspelo preuzimanje installer.py. Proveri internet konekciju."
        exit 1
    fi
fi

# Kreiraj prazan apps-example.json (bez dodatnih aplikacija)
if [ ! -f "apps-example.json" ]; then
    echo "📄 Kreiram apps-example.json..."
    echo '[]' > apps-example.json
fi

# ⭐ Osiguravamo da sajt bude kreiran pod imenom development.localhost
export SITES="development.localhost"

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

DB_NAME=$(python3 -c "import sys, json; f=open('sites/development.localhost/site_config.json'); data=json.load(f); f.close(); print(data['db_name'])")
DB_USER=$DB_NAME
DB_PASSWORD=$(python3 -c "import sys, json; f=open('sites/development.localhost/site_config.json'); data=json.load(f); f.close(); print(data['db_password'])")

echo "   DB_NAME: $DB_NAME"
echo "   DB_USER: $DB_USER"

mysql -h mariadb -u root -p123 -e "GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}'; FLUSH PRIVILEGES;"

if mysql -h mariadb -u "$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1" &>/dev/null; then
    echo "✅ Povezivanje uspešno – privilegije su ispravne."
else
    echo "❌ Ne mogu da se povežem kao $DB_USER. Proveri GRANT komandu."
    exit 1
fi

# Instalacija ERPNext i HRMS (ERPNext prvo, jer HRMS zavisi od njega)
echo "📦 Instaliram ERPNext i HRMS aplikacije..."
if [ -d "apps/erpnext" ]; then
    echo "⚠️ apps/erpnext već postoji, brišem..."
    rm -rf apps/erpnext
fi
if [ -d "apps/hrms" ]; then
    echo "⚠️ apps/hrms već postoji, brišem..."
    rm -rf apps/hrms
fi

bench get-app erpnext --branch version-15
bench get-app hrms --branch version-15

bench --site development.localhost install-app erpnext
bench --site development.localhost install-app hrms
bench build  # Osvežava assets i hookove pre migracije
bench --site development.localhost migrate  # Migracija baze – rešava 'istable' grešku
bench --site development.localhost set-config developer_mode 1

touch logs/bench.log 2>/dev/null || true
chmod 666 logs/bench.log 2>/dev/null || true

if [ -f "/workspace/requirements.txt" ]; then
    echo "📦 Instaliram SaaS monitor dependencies..."
    pip install -r /workspace/requirements.txt
else
    echo "⚠️ requirements.txt nije pronađen, preskačem."
fi

echo "⏰ Podešavam cron za SaaS monitor..."
(crontab -l 2>/dev/null || echo "") | grep -v "saas_monitor.py" | { cat; echo "*/15 * * * * cd /workspace && /usr/local/bin/python saas_monitor.py >> /workspace/saas_monitor.log 2>&1"; } | crontab - 2>/dev/null || echo "⚠️ Cron podešavanje nije uspelo (nije problem)."

echo ""
echo "🎉 ===== SVE JE SPREMNO! ====="
echo "▶️ Sada možeš pokrenuti: cd /workspace/development/frappe-bench && bench start"
echo "🌐 Frappe je dostupan na: http://localhost:8000"
echo "🔑 Login: Administrator / admin"