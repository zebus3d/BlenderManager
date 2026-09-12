#!/usr/bin/env bash
# Construye un AppImage a partir del paquete "one-folder" de PyInstaller.
#
# Uso:  packaging/build_appimage.sh [directorio_dist]
#
# Requisitos: haber ejecutado antes PyInstaller (ver packaging/build.sh) y
# tener wget. appimagetool se descarga automáticamente.
set -euo pipefail

DIST="${1:-dist}"
PACKAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="BlenderManager"
APPDIR="${DIST}/${APP_NAME}.AppDir"

if [ ! -d "${DIST}/${APP_NAME}" ]; then
    echo "No existe ${DIST}/${APP_NAME}. Ejecuta antes PyInstaller." >&2
    exit 1
fi

rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
cp -r "${DIST}/${APP_NAME}/." "${APPDIR}/usr/bin/"

cp "${PACKAGING_DIR}/blendermanager.desktop" "${APPDIR}/blendermanager.desktop"
cp "${PACKAGING_DIR}/../src/assets/images/blender_logo.png" "${APPDIR}/blendermanager.png"

cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/BlenderManager" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

TOOL="${DIST}/appimagetool-x86_64.AppImage"
if [ ! -f "${TOOL}" ]; then
    echo "Descargando appimagetool..."
    wget -q -O "${TOOL}" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "${TOOL}"
fi

OUTPUT="${DIST}/${APP_NAME}-x86_64.AppImage"
# APPIMAGE_EXTRACT_AND_RUN evita depender de FUSE (habitual en contenedores/CI).
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "${TOOL}" "${APPDIR}" "${OUTPUT}"
echo "AppImage creado en ${OUTPUT}"
