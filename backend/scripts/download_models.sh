#!/usr/bin/env bash
# Descarga los modelos de OpenCV Zoo (licencia Apache 2.0) y verifica su integridad.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/models"
mkdir -p "$DIR"
BASE="https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
declare -A FILES=(
  [face_detection_yunet_2023mar.onnx]="face_detection_yunet|8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
  [face_recognition_sface_2021dec.onnx]="face_recognition_sface|0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
)
for name in "${!FILES[@]}"; do
  IFS='|' read -r folder sha <<< "${FILES[$name]}"
  if [[ -f "$DIR/$name" ]] && echo "$sha  $DIR/$name" | sha256sum -c --quiet 2>/dev/null; then
    echo "✓ $name ya existe"; continue
  fi
  echo "↓ Descargando $name…"
  curl -fL --retry 3 -o "$DIR/$name" "$BASE/$folder/$name"
  echo "$sha  $DIR/$name" | sha256sum -c - || { echo "✗ Suma de verificación incorrecta para $name"; rm -f "$DIR/$name"; exit 1; }
done
echo "Modelos listos en $DIR"
