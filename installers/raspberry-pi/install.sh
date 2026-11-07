#!/usr/bin/env bash
# FaceGuard AI para Raspberry Pi — instalador automático.
#
# Instalar o actualizar a la última versión (Raspberry Pi OS 64-bit):
#   curl -fsSL https://raw.githubusercontent.com/Galito1014/FaceGuard/main/installers/raspberry-pi/install.sh | sudo bash
#
# Opciones (después de "bash -s --" si se usa con curl):
#   --version v1.2.0      instalar una versión concreta
#   --csi                 usar una cámara CSI (módulo de cámara oficial) en lugar de USB
#   --file ruta.tar.gz    instalar sin Internet desde un paquete ya descargado
#                         (debe estar junto a SHA256SUMS.txt de la misma versión)
#
# Descarga el paquete de GitHub Releases, comprueba su SHA-256 y ejecuta
# deploy/install.sh, que conserva los datos y la configuración al actualizar.
set -euo pipefail
REPO="${FACEGUARD_REPO:-Galito1014/FaceGuard}"
TAG=""
FILE=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) TAG="$2"; shift 2 ;;
    --file) FILE="$2"; shift 2 ;;
    --csi) EXTRA+=(--csi); shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1"; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Ejecute con sudo:  curl -fsSL … | sudo bash"; exit 1; }
[[ "$(uname -m)" == "aarch64" ]] || { echo "Se necesita Raspberry Pi OS de 64 bits (aarch64). Detectado: $(uname -m)"; exit 1; }
command -v apt-get >/dev/null || { echo "Este instalador es para Raspberry Pi OS / Debian."; exit 1; }
command -v curl >/dev/null || apt-get install -y curl
command -v sha256sum >/dev/null || { echo "Falta sha256sum (coreutils)."; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [[ -n "$FILE" ]]; then
  PKG="$(readlink -f "$FILE")"
  SUMS="$(dirname "$PKG")/SHA256SUMS.txt"
  [[ -f "$SUMS" ]] || { echo "No se encontró $SUMS junto al paquete."; exit 1; }
else
  if [[ -z "$TAG" ]]; then
    echo "==> Buscando la última versión de FaceGuard AI…"
    TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)
    [[ -n "$TAG" ]] || { echo "No se pudo consultar GitHub Releases."; exit 1; }
  fi
  VER="${TAG#v}"
  NAME="FaceGuardAI-RaspberryPi-$VER-arm64.tar.gz"
  BASE="https://github.com/$REPO/releases/download/$TAG"
  echo "==> Descargando $NAME"
  curl -fL --retry 3 -o "$WORK/$NAME" "$BASE/$NAME"
  curl -fsSL --retry 3 -o "$WORK/SHA256SUMS.txt" "$BASE/SHA256SUMS.txt"
  PKG="$WORK/$NAME"
  SUMS="$WORK/SHA256SUMS.txt"
fi

echo "==> Verificando la integridad (SHA-256)"
EXPECTED=$(grep " $(basename "$PKG")\$" "$SUMS" | awk '{print $1}')
[[ -n "$EXPECTED" ]] || { echo "El paquete no aparece en SHA256SUMS.txt."; exit 1; }
ACTUAL=$(sha256sum "$PKG" | awk '{print $1}')
[[ "$EXPECTED" == "$ACTUAL" ]] || { echo "✗ La suma SHA-256 no coincide. Paquete dañado o modificado; no se instala."; exit 1; }
echo "    ✓ $ACTUAL"

mkdir -p "$WORK/src"
tar -xzf "$PKG" -C "$WORK/src" --no-same-owner
SRCDIR="$(find "$WORK/src" -mindepth 1 -maxdepth 1 -type d | head -n1)"
bash "$SRCDIR/deploy/install.sh" "${EXTRA[@]}"
