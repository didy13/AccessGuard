#!/bin/bash
set -e

echo "🔄 Čekam da MariaDB bude spreman..."
until mysqladmin ping -h mariadb -u root -p123 --silent; do
    sleep 2
done

echo "🔄 Podešavam Python 3.11.9 preko pyenv..."
# Ako pyenv nije u PATH-u, dodaj ga
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
pyenv install 3.11.9 -s
pyenv shell 3.11.9

cd /workspace/development

if [ ! -d "frappe-bench" ]; then
    echo "🛠️ Pokrećem Frappe installer..."
    python3 installer.py

    echo "📦 Instaliram HRMS aplikaciju..."
    cd /workspace/development/frappe-bench
    bench get-app hrms --branch version-15
    bench --site development.localhost install-app hrms
else
    echo "✅ Bench već postoji, preskačem inicijalizaciju."
fi

echo "✅ Setup završen! Sada možeš pokrenuti:"
echo "   cd /workspace/development/frappe-bench && bench start"