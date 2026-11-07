#!/usr/bin/env bash
# Instalación y actualización de FaceGuard AI en Raspberry Pi OS 64-bit (Bookworm o posterior).
#
# Normalmente no se ejecuta a mano: lo llama installers/raspberry-pi/install.sh
# después de descargar y verificar la versión publicada. También sirve desde un
# repositorio clonado:   sudo ./deploy/install.sh [--csi]
#
#   --csi   usar una cámara CSI (módulo de cámara oficial) con picamera2 en lugar de USB
#
# Es seguro ejecutarlo de nuevo para actualizar: los datos de /var/lib/faceguard y la
# configuración de /etc/faceguard/faceguard.env se conservan, y antes de cambiar nada
# se guarda una copia de la base de datos.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Ejecute con sudo."; exit 1; }
CSI=0
for arg in "$@"; do
  case "$arg" in
    --csi) CSI=1 ;;
    *) echo "Opción desconocida: $arg"; exit 2 ;;
  esac
done
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/faceguard-ai
DATA=/var/lib/faceguard
ENVF=/etc/faceguard/faceguard.env
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/backend/app/__init__.py")

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "!! Arquitectura $(uname -m): FaceGuard AI para Raspberry Pi requiere Raspberry Pi OS de 64 bits (aarch64)."
  exit 1
fi

echo "==> FaceGuard AI $VERSION"
UPGRADE=0
if systemctl list-unit-files faceguard.service &>/dev/null && [[ -f /etc/systemd/system/faceguard.service ]]; then
  UPGRADE=1
  echo "==> Instalación existente encontrada: se actualizará conservando los datos"
  systemctl stop faceguard || true
  if [[ -f "$DATA/faceguard.db" ]]; then
    BK="$DATA/backups/antes-de-actualizar-$(date +%Y%m%d-%H%M%S).db"
    mkdir -p "$DATA/backups"
    cp -p "$DATA/faceguard.db" "$BK"
    chown faceguard:faceguard "$BK" "$DATA/backups"
    chmod 600 "$BK"
    echo "    Copia de la base de datos: $BK"
  fi
fi

echo "==> Paquetes del sistema"
apt-get update
apt-get install -y python3-venv python3-dev libgl1 curl rsync
# GPIO (LED y buzzer). Si el paquete no existe en esta distribución, se usa el modo simulado.
apt-get install -y python3-lgpio || echo "!! python3-lgpio no disponible: el LED y el buzzer funcionarán en modo simulado"
if [[ $CSI -eq 1 ]]; then apt-get install -y python3-picamera2; fi

echo "==> Usuario de servicio"
id faceguard &>/dev/null || useradd --system --home "$DATA" --shell /usr/sbin/nologin faceguard
getent group gpio >/dev/null || groupadd --system gpio   # existe en Raspberry Pi OS; el servicio lo necesita
usermod -aG video,gpio faceguard

echo "==> Copiando aplicación a $DEST"
mkdir -p "$DEST"
# backend/.env y backend/.venv son de la ejecución manual; el servicio usa $ENVF y $DEST/venv
rsync -a --delete --exclude node_modules --exclude 'backend/data' --exclude 'backend/.env' --exclude 'backend/.venv' \
      --exclude '/venv' --exclude '.git' "$SRC/" "$DEST/"

echo "==> Entorno de Python"
[[ -x "$DEST/venv/bin/python" ]] || python3 -m venv --system-site-packages "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade pip
"$DEST/venv/bin/pip" install -r "$DEST/backend/requirements.txt"

echo "==> Modelos de reconocimiento facial"
bash "$DEST/backend/scripts/download_models.sh"

if [[ ! -f "$DEST/frontend/dist/index.html" ]]; then
  echo "!! No se encontró frontend/dist. Compílelo antes (en la Pi o en otro equipo):"
  echo "   cd frontend && npm ci && npm run build"
fi

echo "==> Datos y configuración"
mkdir -p "$DATA" /etc/faceguard
chown -R faceguard:faceguard "$DATA"
chmod 700 "$DATA"
[[ -f "$ENVF" ]] || cp "$DEST/deploy/faceguard.env.example" "$ENVF"
# Instalaciones anteriores: añade las opciones nuevas sin tocar las existentes.
grep -q '^FACEGUARD_EDITION=' "$ENVF" || echo 'FACEGUARD_EDITION=pi' >> "$ENVF"
grep -q '^FACEGUARD_ALLOWED_NETWORKS=' "$ENVF" || echo 'FACEGUARD_ALLOWED_NETWORKS=local' >> "$ENVF"
if [[ $CSI -eq 1 ]]; then
  if grep -q '^FACEGUARD_CAMERA_BACKEND=' "$ENVF"; then
    sed -i 's/^FACEGUARD_CAMERA_BACKEND=.*/FACEGUARD_CAMERA_BACKEND=picamera2/' "$ENVF"
  else
    echo 'FACEGUARD_CAMERA_BACKEND=picamera2' >> "$ENVF"
  fi
fi
chown root:faceguard "$ENVF"
chmod 640 "$ENVF"

echo "==> Servicio systemd (inicio automático al encender)"
cp "$DEST/deploy/faceguard.service" /etc/systemd/system/faceguard.service
systemctl daemon-reload
systemctl enable faceguard
systemctl restart faceguard

echo "==> Esperando a que FaceGuard AI responda…"
PORT=$(sed -n 's/^FACEGUARD_PORT=//p' "$ENVF" | tail -n1); PORT=${PORT:-8000}
for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
if ! curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "!! El servicio no respondió. Revise: sudo journalctl -u faceguard -n 50"
  exit 1
fi

IP=$(hostname -I | awk '{print $1}')
echo
echo "============================================================"
[[ $UPGRADE -eq 1 ]] && echo " FaceGuard AI actualizado a $VERSION" || echo " FaceGuard AI $VERSION instalado"
echo " Panel:  http://$IP:$PORT   (solo desde la red local)"
if [[ -f "$DATA/secret/setup_code.txt" ]]; then
  echo " Código de configuración inicial:  $(cat "$DATA/secret/setup_code.txt")"
  echo " Ábralo en el navegador y siga el asistente."
fi
echo "============================================================"
