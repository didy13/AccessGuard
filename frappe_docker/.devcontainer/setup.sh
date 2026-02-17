#!/bin/bash
set -e
export UV_LINK_MODE=copy

echo "🔄 Čekam da MariaDB bude spreman..."
until mysqladmin ping -h mariadb -u root -p123 --silent; do
    sleep 2
done

# Podesi pyenv za frappe korisnika
export PYENV_ROOT="/home/frappe/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

echo "🔄 Instaliram Python 3.11.9 (ako već nije)..."
pyenv install 3.11.9 -s
pyenv shell 3.11.9

# Proveri da li je ispravna verzija aktivna
python --version

cd /workspace/development

if [ ! -d "frappe-bench" ]; then
    echo "🛠️ Pokrećem Frappe installer..."
    python3 installer.py

    echo "📦 Instaliram HRMS aplikaciju..."
    cd /workspace/development/frappe-bench
    bench get-app hrms --branch version-15
    bench --site development.localhost install-app hrms
else
    echo "✅ Bench već postoji, preskačem."
fi

echo "✅ Setup završen! Sada možeš pokrenuti: cd /workspace/development/frappe-bench && bench start"