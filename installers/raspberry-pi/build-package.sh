#!/usr/bin/env bash
# Crea el paquete de FaceGuard AI para Raspberry Pi que se publica en GitHub Releases.
# Incluye el núcleo, el panel web ya compilado y los modelos ONNX, para que la Pi
# no necesite Node.js ni descargar los modelos aparte.
# Uso: installers/raspberry-pi/build-package.sh <versión>
set -euo pipefail
VERSION="${1:?Indique la versión, p. ej. 1.1.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/build/release"
NAME="faceguard-ai-$VERSION"
STAGE="$ROOT/build/pi/$NAME"
for f in backend/models/face_detection_yunet_2023mar.onnx backend/models/face_recognition_sface_2021dec.onnx frontend/dist/index.html; do
  [[ -f "$ROOT/$f" ]] || { echo "Falta $f"; exit 1; }
done
rm -rf "$ROOT/build/pi"; mkdir -p "$STAGE" "$OUT"
tar -C "$ROOT" --exclude='__pycache__' --exclude='.pytest_cache' --exclude='backend/data' \
    --exclude='backend/.env' --exclude='backend/.venv' -cf - backend | tar -C "$STAGE" -xf -
mkdir -p "$STAGE/frontend"
cp -a "$ROOT/frontend/dist" "$STAGE/frontend/dist"
cp -a "$ROOT/deploy" "$STAGE/deploy"
mkdir -p "$STAGE/installers"
cp -a "$ROOT/installers/raspberry-pi" "$STAGE/installers/raspberry-pi"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$ROOT/README.md" "$ROOT/PRIVACY.md" "$ROOT/SECURITY.md" "$STAGE/"
TAR="$OUT/FaceGuardAI-RaspberryPi-$VERSION-arm64.tar.gz"
tar --owner=0 --group=0 -czf "$TAR" -C "$ROOT/build/pi" "$NAME"
echo "Listo: $TAR"
