#!/usr/bin/env bash
# Empaqueta FaceGuard AI Desktop para Linux x86_64 como AppImage y como .deb.
# Requiere la carpeta generada por PyInstaller (build/dist/FaceGuardAI).
# Uso: installers/linux/build-linux.sh <versión>     p. ej. 1.1.0
set -euo pipefail
VERSION="${1:?Indique la versión, p. ej. 1.1.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/build/dist/FaceGuardAI"
OUT="$ROOT/build/release"
WORK="$ROOT/build/linux"
ARCH_DEB=amd64
[[ -x "$SRC/FaceGuardAI" ]] || { echo "No existe $SRC/FaceGuardAI. Ejecute PyInstaller primero."; exit 1; }
rm -rf "$WORK"; mkdir -p "$WORK" "$OUT"

# ------------------------------------------------------------------ .deb
PKG="$WORK/deb"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/faceguard-ai" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/doc/faceguard-ai"
cp -a "$SRC/." "$PKG/opt/faceguard-ai/"
ln -s /opt/faceguard-ai/FaceGuardAI "$PKG/usr/bin/faceguard-ai"
cp "$ROOT/installers/linux/faceguard-ai.desktop" "$PKG/usr/share/applications/"
cp "$ROOT/installers/assets/faceguard.png" "$PKG/usr/share/icons/hicolor/256x256/apps/faceguard-ai.png"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/faceguard-ai/copyright"
SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CTRL
Package: faceguard-ai
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH_DEB
Installed-Size: $SIZE
Depends: xdg-utils
Recommends: chromium | chromium-browser | google-chrome-stable | microsoft-edge-stable
Maintainer: FaceGuard AI <https://github.com/Galito1014/FaceGuard/issues>
Homepage: https://github.com/Galito1014/FaceGuard
Description: FaceGuard AI Desktop — alertas por reconocimiento facial con procesamiento local
 Detecta rostros con una cámara USB o integrada y avisa cuando hay una posible
 coincidencia con la lista de alerta. Todo se procesa en el equipo, sin Internet.
 Los datos del usuario se guardan en ~/.local/share/faceguard-ai y no se borran al
 actualizar o desinstalar el paquete.
CTRL
cat > "$PKG/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
exit 0
POST
chmod 755 "$PKG/DEBIAN/postinst"
DEB="$OUT/FaceGuardAI-Desktop-$VERSION-linux-amd64.deb"
dpkg-deb --root-owner-group --build "$PKG" "$DEB"

# -------------------------------------------------------------- AppImage
APPDIR="$WORK/FaceGuardAI.AppDir"
mkdir -p "$APPDIR/usr/lib/faceguard-ai"
cp -a "$SRC/." "$APPDIR/usr/lib/faceguard-ai/"
cp "$ROOT/installers/linux/faceguard-ai.desktop" "$APPDIR/faceguard-ai.desktop"
cp "$ROOT/installers/assets/faceguard.png" "$APPDIR/faceguard-ai.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/faceguard-ai/FaceGuardAI" "$@"
RUN
chmod 755 "$APPDIR/AppRun"
TOOL="${APPIMAGETOOL:-$WORK/appimagetool}"
if [[ ! -x "$TOOL" ]]; then
  curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
APPIMAGE="$OUT/FaceGuardAI-Desktop-$VERSION-linux-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$APPIMAGE"
chmod +x "$APPIMAGE"
echo "Listo: $DEB y $APPIMAGE"
