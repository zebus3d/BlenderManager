#!/bin/sh
# Lanza BlenderManager en desarrollo usando el venv del proyecto.
#
#   ./run.sh                 -> abre la interfaz
#   ./run.sh --smoke         -> lista builds por consola
#   ./run.sh --screenshot X  -> captura y sale
#
# Si falta el venv, lo crea e instala las dependencias.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [ ! -x .venv/bin/python ]; then
    echo "Creando entorno virtual (.venv)..."
    python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python src/main.py "$@"
