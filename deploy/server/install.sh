#!/usr/bin/env bash
# Instala o actualiza el despliegue automático, el watchdog de WhatsApp y el auto-heal
# del contenedor Evolution en el VPS.
# Ejecutar como root desde el repositorio (usa deploy/server y server-config):
#   bash install.sh <llave pública de GitHub Actions (.pub)>
# Es idempotente: se puede volver a correr para actualizar los scripts.
set -euo pipefail
cd "$(dirname "$0")"

ACTIONS_PUBKEY_FILE="${1:?uso: install.sh <llave pública de GitHub Actions>}"
GITHUB_ED25519_FP="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
STATE="/var/lib/tnl-deploy"
SECRET_KEY_FILE="/opt/tunegociolisto/configs/django-secrets/secret_key"
UNITS="../../server-config/etc/systemd/system"
WATCHDOG_UNITS="tnl-whatsapp-watchdog.service tnl-whatsapp-watchdog.timer"
AUTOHEAL_UNITS="tnl-evolution-autoheal.service tnl-evolution-autoheal.timer"

[ "$(id -u)" = 0 ] || { echo "Ejecutar como root"; exit 1; }
grep -q '^ssh-ed25519 ' "$ACTIONS_PUBKEY_FILE" || { echo "Llave pública inválida"; exit 1; }
for unit in $WATCHDOG_UNITS $AUTOHEAL_UNITS; do
    [ -f "$UNITS/$unit" ] || { echo "Falta $UNITS/$unit (ejecutar desde el repositorio completo)"; exit 1; }
done

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

# 7. Watchdog de WhatsApp: servicio (usuario tnl) y timer cada 60 s.
#    El timer se habilita solo en la primera instalación: volver a correr este script
#    no reactiva un watchdog que se detuvo o deshabilitó a propósito.
WATCHDOG_NUEVO=0
[ -f /etc/systemd/system/tnl-whatsapp-watchdog.timer ] || WATCHDOG_NUEVO=1
for unit in $WATCHDOG_UNITS; do
    install -o root -g root -m 0644 "$UNITS/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
if [ "$WATCHDOG_NUEVO" = 1 ]; then
    systemctl enable --now tnl-whatsapp-watchdog.timer
fi
echo "Watchdog WhatsApp: $(systemctl is-enabled tnl-whatsapp-watchdog.timer || true)," \
    "$(systemctl is-active tnl-whatsapp-watchdog.timer || true)"

# 8. Auto-heal del contenedor Evolution (root, por el acceso a Docker) con timer cada 60 s.
#    Igual que el watchdog: el timer se habilita solo en la primera instalación.
AUTOHEAL_NUEVO=0
[ -f /etc/systemd/system/tnl-evolution-autoheal.timer ] || AUTOHEAL_NUEVO=1
install -o root -g root -m 0755 tnl-evolution-autoheal /usr/local/sbin/tnl-evolution-autoheal
for unit in $AUTOHEAL_UNITS; do
    install -o root -g root -m 0644 "$UNITS/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
if [ "$AUTOHEAL_NUEVO" = 1 ]; then
    systemctl enable --now tnl-evolution-autoheal.timer
fi
echo "Auto-heal Evolution: $(systemctl is-enabled tnl-evolution-autoheal.timer || true)," \
    "$(systemctl is-active tnl-evolution-autoheal.timer || true)"

echo
echo "Listo. Llave para GitHub -> Settings -> Deploy keys (solo lectura, sin 'Allow write access'):"
cat "$STATE/ssh/github_ed25519.pub"
