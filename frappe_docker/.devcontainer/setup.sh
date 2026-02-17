#!/bin/bash
set -e

echo "🔄 Čekam da MariaDB bude spreman..."
until mysqladmin ping -h mariadb -u root -p123 --silent; do
    sleep 2
done

cd /workspace/development

if [ ! -d "frappe-bench" ]; then
    echo "🛠️ Kreiram novi Frappe bench (version-15)..."
    bench init frappe-bench --frappe-branch version-15 --python "$(which python)" --skip-redis-config-generation
    cd frappe-bench
    bench set-mariadb-host mariadb
    bench set-redis-cache-host redis-cache:6379
    bench set-redis-queue-host redis-queue:6379
    bench set-redis-socketio-host redis-queue:6379

    echo "🌐 Kreiram sajt 'development.localhost'..."
    bench new-site development.localhost \
        --mariadb-root-password 123 \
        --admin-password admin \
        --db-root-password 123 \
        --db-name development
else
    echo "✅ Bench već postoji, preskačem."
fi

echo "✅ Setup završen! Sada možeš pokrenuti 'bench start' u /workspace/development/frappe-bench"