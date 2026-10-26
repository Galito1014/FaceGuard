#!/usr/bin/env bash
# Instalación de FaceGuard AI en Raspberry Pi OS 64-bit (Bookworm o posterior).
# Uso:  sudo ./deploy/install.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecute con sudo."; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/faceguard-ai

echo "==> Paquetes del sistema"
apt-get update
apt-get install -y python3-venv python3-dev python3-lgpio libgl1 curl rsync

echo "==> Usuario de servicio"
id faceguard &>/dev/null || useradd --system --home /var/lib/faceguard --shell /usr/sbin/nologin faceguard
usermod -aG video,gpio faceguard

echo "==> Copiando aplicación a $DEST"
mkdir -p "$DEST"
rsync -a --delete --exclude node_modules --exclude 'backend/data' --exclude '.git' "$SRC/" "$DEST/"

echo "==> Entorno de Python"
python3 -m venv --system-site-packages "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade pip
"$DEST/venv/bin/pip" install -r "$DEST/backend/requirements.txt"

echo "==> Modelos de reconocimiento facial"
bash "$DEST/backend/scripts/download_models.sh"

if [[ ! -f "$DEST/frontend/dist/index.html" ]]; then
  echo "!! No se encontró frontend/dist. Compílelo antes (en la Pi o en otro equipo):"
  echo "   cd frontend && npm ci && npm run build"
fi

echo "==> Datos y configuración"
mkdir -p /var/lib/faceguard /etc/faceguard
chown -R faceguard:faceguard /var/lib/faceguard
chmod 700 /var/lib/faceguard
[[ -f /etc/faceguard/faceguard.env ]] || cp "$DEST/deploy/faceguard.env.example" /etc/faceguard/faceguard.env
chmod 640 /etc/faceguard/faceguard.env

echo "==> Servicio systemd"
cp "$DEST/deploy/faceguard.service" /etc/systemd/system/faceguard.service
systemctl daemon-reload
systemctl enable --now faceguard
sleep 4
systemctl --no-pager status faceguard | head -n 12 || true

IP=$(hostname -I | awk '{print $1}')
echo
echo "FaceGuard AI instalado. Abra http://$IP:8000 desde un equipo de la red local."
echo "Credenciales iniciales: sudo cat /var/lib/faceguard/secret/initial_admin.txt"
