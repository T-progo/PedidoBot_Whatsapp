#!/usr/bin/env bash
# Instala o actualiza el despliegue automático en el VPS. Ejecutar como root:
#   bash install.sh <llave pública de GitHub Actions (.pub)>
# Es idempotente: se puede volver a correr para actualizar los scripts.
set -euo pipefail
cd "$(dirname "$0")"

ACTIONS_PUBKEY_FILE="${1:?uso: install.sh <llave pública de GitHub Actions>}"
GITHUB_ED25519_FP="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
STATE="/var/lib/tnl-deploy"
SECRET_KEY_FILE="/opt/tunegociolisto/configs/django-secrets/secret_key"

[ "$(id -u)" = 0 ] || { echo "Ejecutar como root"; exit 1; }
grep -q '^ssh-ed25519 ' "$ACTIONS_PUBKEY_FILE" || { echo "Llave pública inválida"; exit 1; }

# 1. Scripts, propiedad de root y fuera de /opt/tunegociolisto (la app no puede modificarlos)
install -o root -g root -m 0755 tnl-deploy-django /usr/local/sbin/tnl-deploy-django
install -o root -g root -m 0755 tnl-deploy-ssh-entry /usr/local/bin/tnl-deploy-ssh-entry

# 2. Directorios de estado, respaldos y logs
install -d -o root -g tnl -m 0710 "$STATE"
install -d -o root -g root -m 0700 "$STATE/ssh"
install -d -o root -g tnl -m 0750 "$STATE/work"
install -d -o root -g root -m 0700 /var/backups/tnl-deploy
install -d -o root -g root -m 0750 /var/log/tnl-deploy

# 3. Usuario deploy: sin contraseña; su única llave solo puede lanzar el despliegue
if ! id deploy >/dev/null 2>&1; then
    useradd --system --create-home --home-dir /home/deploy --shell /bin/bash deploy
fi
usermod -p '*' deploy
install -d -o root -g root -m 0755 /home/deploy/.ssh
printf 'restrict,command="/usr/local/bin/tnl-deploy-ssh-entry" %s\n' \
    "$(head -1 "$ACTIONS_PUBKEY_FILE")" > /home/deploy/.ssh/authorized_keys
chown root:root /home/deploy/.ssh/authorized_keys
chmod 0644 /home/deploy/.ssh/authorized_keys

# 4. sudo: deploy solo puede ejecutar el script de despliegue
printf 'deploy ALL=(root) NOPASSWD: /usr/local/sbin/tnl-deploy-django\n' > /etc/sudoers.d/tnl-deploy.tmp
chmod 0440 /etc/sudoers.d/tnl-deploy.tmp
visudo -cqf /etc/sudoers.d/tnl-deploy.tmp
mv /etc/sudoers.d/tnl-deploy.tmp /etc/sudoers.d/tnl-deploy

# 5. Llave del servidor hacia GitHub (Deploy key de solo lectura) y huella verificada de github.com
if [ ! -f "$STATE/ssh/github_ed25519" ]; then
    ssh-keygen -q -t ed25519 -N '' -C "tnl-vps-deploy-readonly" -f "$STATE/ssh/github_ed25519"
fi
ssh-keyscan -t ed25519 github.com 2>/dev/null > "$STATE/ssh/known_hosts.tmp"
FP="$(ssh-keygen -lf "$STATE/ssh/known_hosts.tmp" | awk '{print $2}')"
[ "$FP" = "$GITHUB_ED25519_FP" ] || { echo "Huella de github.com inesperada: $FP"; exit 1; }
mv "$STATE/ssh/known_hosts.tmp" "$STATE/ssh/known_hosts"

# 6. SECRET_KEY de Django en archivo (settings.py la lee de ahí). Solo la primera vez:
#    se toma el valor que hoy está escrito en settings.py para no invalidar sesiones.
if [ ! -f "$SECRET_KEY_FILE" ]; then
    python3 - "$SECRET_KEY_FILE" <<'PY'
import os, re, sys
src = open("/opt/tunegociolisto/apps/admin/config/settings.py", encoding="utf-8").read()
m = re.search(r"^SECRET_KEY = '([^']+)'$", src, re.M)
if not m or m.group(1).startswith("<REDACTED"):
    sys.exit("No se encontró la SECRET_KEY en settings.py")
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
with os.fdopen(fd, "w") as f:
    f.write(m.group(1) + "\n")
PY
    chown root:tnl "$SECRET_KEY_FILE"
    chmod 0640 "$SECRET_KEY_FILE"
    echo "SECRET_KEY guardada en $SECRET_KEY_FILE"
fi

echo
echo "Listo. Llave para GitHub -> Settings -> Deploy keys (solo lectura, sin 'Allow write access'):"
cat "$STATE/ssh/github_ed25519.pub"
