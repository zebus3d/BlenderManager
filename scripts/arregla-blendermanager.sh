#!/bin/bash
# ÚNICO script de diagnóstico + arreglo para BlenderManager.
# Uso:   bash arregla-blendermanager.sh > resultado.txt 2>&1
# Manda resultado.txt entero.
#
# Hace todo:
#   A. Encuentra todas las AppImages de BlenderManager en tu HOME
#   B. Les pone bit de ejecución (bug conocido del updater)
#   C. Prueba cada una: modo API (--smoke) y modo VENTANA REAL (--screenshot)
#   D. Si el .desktop apunta a una ruta rota, lo dice
#   E. Si encuentra una que abre ventana, la copia sobre la instalada
#      (haciendo copia de seguridad de la anterior)
#   F. Deja un resumen claro

set -u

HOME_DIR="$HOME"
SHOT="/tmp/bm-shot-$$.png"

echo "############################################"
echo "# BlenderManager: diagnóstico y arreglo    #"
echo "# $(date)                                  #"
echo "############################################"
echo "Usuario: $USER"
echo "Sesión:  ${XDG_SESSION_TYPE:-desconocida}"
echo "Sistema: $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '\"')"
echo "glibc:   $(ldd --version 2>&1 | head -1)"
echo ""

echo "============================================"
echo "A. AppImages de BlenderManager encontradas"
echo "============================================"
mapfile -t FOUND < <(find "$HOME_DIR" -maxdepth 6 \
    -name "Blender*Manager*.AppImage" -type f 2>/dev/null | sort -u)
if [ ${#FOUND[@]} -eq 0 ]; then
    echo "  NINGUNA. ¿Está en otro sitio? Pásame el resultado igual."
    echo "RESULTADO: sin_appimages"
    exit 0
fi
for f in "${FOUND[@]}"; do
    perm=$(stat -c "%A" "$f")
    mtime=$(stat -c "%y" "$f" | cut -d. -f1)
    size=$(stat -c "%s" "$f")
    echo "  $perm  $((size/1024/1024)) MB  $mtime"
    echo "      $f"
done

echo ""
echo "============================================"
echo "B. Poniendo bit +x donde falte"
echo "============================================"
for f in "${FOUND[@]}"; do
    if [ ! -x "$f" ]; then
        chmod +x "$f" 2>/dev/null \
            && echo "  +x aplicado: $f" \
            || echo "  FALLO chmod: $f"
    else
        echo "  ya ejecutable: $f"
    fi
done

echo ""
echo "============================================"
echo "C. Probando cada AppImage"
echo "============================================"
declare -a WORKING=()
declare -a FAILING=()
for f in "${FOUND[@]}"; do
    echo "--------------------------------------------"
    echo "PROBANDO: $f"
    echo "--------------------------------------------"

    echo "  [C1] --smoke (lista de builds, no abre ventana)"
    OUT1=$(APPIMAGE_EXTRACT_AND_RUN=1 "$f" --smoke 2>&1)
    CODE1=$?
    echo "$OUT1" | grep -E "total builds|Traceback|Error|error|cannot|not found|No module" | head -6
    echo "       exit=$CODE1"

    echo "  [C2] ventana real (tarda ~8s: abre, captura y cierra)"
    rm -f "$SHOT"
    OUT2=$(timeout 30 env APPIMAGE_EXTRACT_AND_RUN=1 "$f" --screenshot "$SHOT" 2>&1)
    CODE2=$?
    # Mostramos solo las líneas relevantes (no todo el ruido de Kivy).
    echo "$OUT2" | grep -iE "OpenGL version|OpenGL renderer|Provider:|error|critical|no matching|failed|traceback|segmentation|cannot|abort" | head -12
    echo "       exit=$CODE2"
    # La ventana está OK si Kivy logró crear el contexto GL (aparece
    # "OpenGL version") y NO sale ningún error de provider. El PNG es poco
    # fiable (a veces no se escribe), así que no lo usamos como criterio.
    if echo "$OUT2" | grep -qE "OpenGL version" && \
       ! echo "$OUT2" | grep -qiE "no matching fb config|Unable to find any valuable Window provider|segmentation|Traceback"; then
        echo "       RESULTADO: VENTANA OK"
        WORKING+=("$f")
    else
        echo "       RESULTADO: ventana NO se abrió"
        FAILING+=("$f")
    fi
    rm -f "$SHOT"
done

echo ""
echo "============================================"
echo "D. .desktop (accesos del menú)"
echo "============================================"
shopt -s nullglob
for d in "$HOME_DIR"/.local/share/applications/*blender*manager*.desktop; do
    echo "  Fichero: $d"
    grep -E "Exec=|TryExec=|Icon=" "$d" 2>/dev/null | sed 's/^/      /'
    exec_path=$(grep -oP '(?<=^Exec=).*' "$d" 2>/dev/null | tr -d '"' | awk '{print $1}')
    if [ -n "$exec_path" ]; then
        if [ -f "$exec_path" ]; then
            echo "      -> el binario referenciado EXISTE"
        else
            echo "      -> OJO: el binario referenciado NO EXISTE ($exec_path)"
        fi
    fi
done
[ -z "$(ls "$HOME_DIR"/.local/share/applications/*blender*manager*.desktop 2>/dev/null)" ] \
    && echo "  (no hay .desktop de BlenderManager)"

echo ""
echo "============================================"
echo "E. Arreglo automático"
echo "============================================"
if [ ${#WORKING[@]} -eq 0 ]; then
    echo "  Ninguna AppImage abre ventana. No puedo arreglar automáticamente."
    echo "  Manda este fichero entero y lo arreglo en el código."
elif [ ${#WORKING[@]} -eq 1 ]; then
    echo "  Solo funciona: ${WORKING[0]}"
    echo "  (no hay nada que reemplazar si solo hay una)"
else
    echo "  Funcionan ${#WORKING[@]}:"
    for w in "${WORKING[@]}"; do echo "    - $w"; done
fi

# Si la instalada (fuera de la caché) falla pero una de la caché funciona,
# copiamos la que funciona sobre la instalada, con copia de seguridad.
INSTALLED=""
for f in "${FOUND[@]}"; do
    case "$f" in
        */.cache/*) ;;
        *) [ -z "$INSTALLED" ] && INSTALLED="$f" ;;
    esac
done

BEST=""
for w in "${WORKING[@]}"; do
    case "$w" in
        */.cache/*) [ -z "$BEST" ] && BEST="$w" ;;
        *) BEST="$w"; break ;;
    esac
done

if [ -n "$INSTALLED" ] && [ -n "$BEST" ] && [ "$INSTALLED" != "$BEST" ]; then
    echo ""
    echo "  La instalada ($INSTALLED) falla y '$BEST' funciona."
    echo "  Reemplazando la instalada por la que funciona..."
    cp -f "$INSTALLED" "$INSTALLED.bak-$(date +%s)" 2>/dev/null \
        && echo "     copia de seguridad creada" \
        || echo "     (no pude crear copia de seguridad)"
    if cp -f "$BEST" "$INSTALLED" 2>/dev/null; then
        chmod +x "$INSTALLED"
        # Verificar de nuevo
        rm -f "$SHOT"
        timeout 30 env APPIMAGE_EXTRACT_AND_RUN=1 "$INSTALLED" --screenshot "$SHOT" >/dev/null 2>&1
        if [ -f "$SHOT" ]; then
            echo "     >>> ARREGLADO: $INSTALLED ya abre ventana"
            rm -f "$SHOT"
        else
            echo "     >>> la copia no abre ventana (raro). Manda este fichero."
        fi
    else
        echo "     FALLO al copiar (¿permisos del directorio?)"
    fi
fi

echo ""
echo "============================================"
echo "F. RESUMEN"
echo "============================================"
echo "  Encontradas:      ${#FOUND[@]}"
echo "  Abren ventana:    ${#WORKING[@]}"
echo "  NO abren:         ${#FAILING[@]}"
echo ""
if [ ${#WORKING[@]} -gt 0 ]; then
    echo "  FUNCIONA: ${WORKING[0]}"
    echo "  Ábrela con doble clic o desde el menú."
else
    echo "  NINGUNA ABRE. Manda el fichero entero para arreglar el binario."
fi
echo "--------------------------------------------"
echo "Fin del diagnóstico."
