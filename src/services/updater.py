"""Comprobación e instalación de actualizaciones desde GitHub Releases.

La aplicación consulta la última release publicada, compara su versión con
``version.__version__`` y, si hay una nueva, descarga el binario de la
plataforma actual y lo instala.

Solo usamos la biblioteca estándar (urllib). La API de GitHub exige un
``User-Agent`` y permite 60 peticiones por hora sin autenticar; usamos ETag
para que las comprobaciones repetidas devuelvan 304 (que no consumen cuota).

Aplicar la actualización es distinto en cada plataforma:

* **Linux AppImage**: se reemplaza el propio archivo ``$APPIMAGE`` y se relanza.
* **Windows**: no se puede sobrescribir un .exe en ejecución, así que se
  extrae la release en un directorio temporal y se relanza el binario *nuevo*
  con ``--apply-update``; ese proceso espera a que salga el actual, copia los
  ficheros y arranca la versión nueva.
* **macOS** (y cualquier caso no soportado): solo se avisa y se revela la
  descarga, porque reemplazar un .app sin firmar es poco fiable.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import version
from services.downloader import log
from services.extractor import extract
from services.settings import cache_dir, write_json_atomic

REPO = "zebus3d/BlenderManager"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
USER_AGENT = f"BlenderManager/{version.__version__} (+https://github.com/{REPO})"

# Un asset por plataforma. El nombre debe coincidir con lo que sube el CI.
ASSET_NAMES = {
    "linux": "BlenderManager-x86_64.AppImage",
    "windows": "BlenderManager-windows-x86_64.zip",
    "darwin": "BlenderManager-macos.zip",
}
CHECKSUM_NAME = "checksums.txt"
EXE_NAME = "BlenderManager.exe" if sys.platform.startswith("win") else "BlenderManager"

_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def updates_dir() -> Path:
    """Carpeta donde se descargan y preparan las actualizaciones."""
    return cache_dir() / "updates"


# --- Comprobación de versión ------------------------------------------------

def _version_key(text: str):
    """Convierte 'v1.2.3' en (1, 2, 3) para poder comparar."""
    key = []
    for chunk in (text or "").strip().lstrip("vV").split("."):
        digits = re.findall(r"\d+", chunk)
        key.append(int(digits[0]) if digits else 0)
    return tuple(key)


def is_newer(current: str, latest: str) -> bool:
    """True si ``latest`` es más nueva que ``current``."""
    if not latest:
        return False
    return _version_key(latest) > _version_key(current)


def asset_for(system) -> str:
    """Nombre del asset que corresponde a esta plataforma (o None)."""
    os_name = getattr(system, "os_name", system) or ""
    return ASSET_NAMES.get(os_name)


def _parse_release(payload: dict):
    """Extrae (tag, assets) del JSON de una release de GitHub."""
    tag = str(payload.get("tag_name") or "")
    assets = []
    for item in payload.get("assets") or []:
        assets.append({
            "name": str(item.get("name") or ""),
            "url": str(item.get("browser_download_url") or ""),
        })
    return tag, assets


def _release_cache():
    base = updates_dir()
    return base / "release.json", base / "release.etag"


def latest_release(force: bool = False, timeout: int = 15):
    """Última release como (tag, assets), o None si no se puede consultar.

    Si ya hay una respuesta cacheada, envía su ETag; cuando GitHub responde 304
    reutilizamos el JSON guardado (y esa petición no gasta cuota).
    """
    json_path, etag_path = _release_cache()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    etag = ""
    if etag_path.is_file():
        try:
            etag = etag_path.read_text(encoding="utf-8").strip()
        except OSError:
            etag = ""
    if etag and not force:
        headers["If-None-Match"] = etag

    request = urllib.request.Request(API_URL, headers=headers)
    new_etag = etag
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            new_etag = response.headers.get("ETag") or etag
    except urllib.error.HTTPError as error:
        if error.code == 304 and json_path.is_file():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        else:
            log(f"update check failed: {error}")
            return None
    except Exception as error:
        log(f"update check failed: {error}")
        return None

    try:
        write_json_atomic(json_path, payload)
        if new_etag:
            etag_path.write_text(new_etag, encoding="utf-8")
    except OSError:
        pass
    return _parse_release(payload)


def checksum_for(assets, filename: str, timeout: int = 15):
    """SHA-256 de ``filename`` según checksums.txt de la release (o None)."""
    url = next((a["url"] for a in assets if a["name"] == CHECKSUM_NAME), None)
    if not url:
        return None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", "replace")
    except Exception as error:
        log(f"checksum fetch failed: {error}")
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and Path(parts[1].lstrip("*")).name == filename:
            return parts[0]
    return None


# --- Aplicar la actualización ----------------------------------------------

def _open_fallback(path=None) -> None:
    """Abre la descarga o la página de releases para actualizar a mano."""
    try:
        if path and sys.platform == "darwin" and Path(path).exists():
            subprocess.Popen(["open", "-R", str(path)])
            return
        if sys.platform.startswith("win"):
            os.startfile(RELEASES_URL)  # noqa: S606 (solo Windows)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", RELEASES_URL])
        else:
            subprocess.Popen(["xdg-open", RELEASES_URL])
    except Exception as error:
        log(f"open fallback failed: {error}")


def _apply_appimage(archive: Path) -> bool:
    """Reemplaza la AppImage en disco y relanza esa versión nueva."""
    target = Path(os.environ.get("APPIMAGE", "")).resolve()
    if not target.exists():
        return False
    try:
        tmp = target.parent / (target.name + ".new")
        shutil.copy2(archive, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    except OSError as error:
        log(f"appimage update failed: {error}")
        return False
    try:
        subprocess.Popen([str(target)], start_new_session=True, close_fds=True)
    except OSError as error:
        log(f"appimage relaunch failed: {error}")
        return False
    return True


def _apply_windows(archive: Path) -> bool:
    """Extrae la release y lanza el binario nuevo en modo --apply-update."""
    app_dir = Path(sys.executable).resolve().parent
    staging = updates_dir() / f"staging-{int(time.time())}"
    try:
        folder = extract(archive, staging)
    except Exception as error:
        log(f"windows update extract failed: {error}")
        shutil.rmtree(staging, ignore_errors=True)
        return False
    helper = folder / EXE_NAME
    if not helper.is_file():
        candidates = list(folder.rglob(EXE_NAME))
        if not candidates:
            log("windows update helper not found")
            shutil.rmtree(staging, ignore_errors=True)
            return False
        helper = candidates[0]
    try:
        subprocess.Popen(
            [str(helper), "--apply-update", str(app_dir), str(os.getpid())],
            creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except OSError as error:
        log(f"windows update launch failed: {error}")
        return False
    return True


def apply(path) -> bool:
    """Instala la actualización descargada.

    Devuelve True si hay que cerrar la aplicación para completarla (ya se ha
    lanzado la versión nueva o el proceso que la aplicará).
    """
    archive = Path(path)
    if not getattr(sys, "frozen", False):
        # En modo fuente no hay nada que reemplazar: avisamos.
        _open_fallback(archive)
        return False
    if os.environ.get("APPIMAGE"):
        return _apply_appimage(archive)
    if sys.platform.startswith("win"):
        return _apply_windows(archive)
    _open_fallback(archive)
    return False


# --- Modo --apply-update (Windows) -----------------------------------------

def _pid_alive(pid: int) -> bool:
    if sys.platform.startswith("win"):
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception:
            return False
        return str(pid) in output.decode("utf-8", "ignore")
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for_exit(pid: int, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.5)


def _copy_tree(source: Path, target: Path) -> None:
    for root, _dirs, files in os.walk(source):
        relative = Path(root).relative_to(source)
        (target / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            try:
                shutil.copy2(Path(root) / name, target / relative / name)
            except OSError as error:
                log(f"update copy failed: {error}")


def apply_update(app_dir, pid) -> None:
    """Espera al proceso antiguo, copia los ficheros nuevos y relanza.

    Se ejecuta desde el binario *nuevo* (extraído en staging), por lo que este
    proceso puede sobrescribir sin problema al .exe antiguo, que ya no corre.
    """
    target = Path(app_dir)
    source = Path(sys.executable).resolve().parent
    try:
        # Este proceso no tiene ventana ni consola: un PID mal formado no
        # puede abortar la actualización en silencio, así que lo registramos
        # y copiamos igualmente (la app antigua ya se está cerrando).
        _wait_for_exit(int(pid))
    except (TypeError, ValueError):
        log(f"update: pid invalido ({pid!r}), copiando sin esperar")
    _copy_tree(source, target)
    exe = target / EXE_NAME
    try:
        subprocess.Popen([str(exe)], close_fds=True)
    except OSError as error:
        log(f"update relaunch failed: {error}")


def cleanup_staging() -> None:
    """Borra los restos de actualizaciones ya aplicadas.

    Son los directorios de staging de Windows y los binarios descargados
    (una AppImage ronda los 60 MB), que hasta ahora se quedaban en el caché
    para siempre. El JSON y el ETag de la release sí se conservan: son
    diminutos y evitan gastar cuota de la API de GitHub.
    """
    base = updates_dir()
    if not base.is_dir():
        return
    keep = {"release.json", "release.etag"}
    for entry in base.iterdir():
        if entry.name in keep:
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                entry.unlink()
            except OSError:
                pass


def cleanup_partials(dest_folder) -> None:
    """Borra descargas de Blender interrumpidas (.part) de la carpeta destino."""
    try:
        folder = Path(dest_folder).expanduser()
        if not folder.is_dir():
            return
        for entry in folder.glob("*.part"):
            try:
                entry.unlink()
            except OSError:
                pass
    except OSError:
        pass
