"""Descarga de archivos en segundo plano con progreso y verificación.

La descarga se hace siempre en un hilo aparte para no congelar la interfaz;
las llamadas de vuelta (progreso, fin, error) las recibe quien nos llame y es
su responsabilidad reenviarlas al hilo de Kivy con ``Clock.schedule_once``.
"""

import hashlib
import threading
import urllib.request
from pathlib import Path

from services import tls
from services.settings import cache_dir

USER_AGENT = "BlenderManager/0.2 (+https://github.com/zebus3d/BlenderManager)"
CHUNK_SIZE = 1024 * 256  # 256 KiB por lectura


def log(message: str) -> None:
    """Registro sencillo a archivo, útil para diagnosticar fallos en otros equipos."""
    try:
        path = cache_dir() / "blendermanager.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        pass


class DownloadError(Exception):
    """Error de descarga, con el mensaje ya listo para mostrar."""
    pass


class Downloader:
    """Gestor de una única descarga simultánea, cancelable."""

    def __init__(self):
        self._cancel = threading.Event()
        self._thread = None

    def cancel(self) -> None:
        """Pide a la descarga en curso que se detenga."""
        self._cancel.set()

    @property
    def running(self) -> bool:
        """True mientras haya una descarga en marcha."""
        return self._thread is not None and self._thread.is_alive()

    def start(self, url, dest_folder, filename, expected_sha256=None,
              on_progress=None, on_done=None, on_error=None) -> None:
        """Lanza la descarga en un hilo aparte y va avisando por callbacks."""
        if self.running:
            return
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(url, dest_folder, filename, expected_sha256, on_progress, on_done, on_error),
            daemon=True,
        )
        self._thread.start()

    def _run(self, url, dest_folder, filename, expected_sha256, on_progress, on_done, on_error):
        # Descargamos primero a un .part y solo al final renombramos,
        # así una descarga a medias no se confunde con una completa.
        part_path = Path(dest_folder).expanduser() / (filename + ".part")
        try:
            dest = Path(dest_folder).expanduser()
            dest.mkdir(parents=True, exist_ok=True)
            final_path = dest / filename
            # La URL va al log: un fallo de red (handshake TLS, host bloqueado)
            # es indistinguible de otro sin saber a qué host iba.
            log(f"downloading {url} -> {final_path}")
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            # Con contexto explicito: si no, en Arch no encuentra las CAs y no
            # se puede descargar nada (ver services/tls.py).
            with urllib.request.urlopen(request, timeout=30,
                                        context=tls.ssl_context()) as response:
                total = int(response.headers.get("Content-Length") or 0)
                digest = hashlib.sha256()
                downloaded = 0
                with open(part_path, "wb") as handle:
                    while True:
                        if self._cancel.is_set():
                            raise DownloadError("cancelled")
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if on_progress:
                            on_progress(downloaded, total)
            if self._cancel.is_set():
                raise DownloadError("cancelled")
            # Verificación de integridad si la API nos dio la suma SHA-256.
            if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
                raise DownloadError("checksum")
            if final_path.exists():
                final_path.unlink()
            part_path.replace(final_path)
            # Bit de ejecución: si el fichero es una AppImage (o cualquier
            # binario) el usuario puede querer abrirlo directamente. El
            # updater hace su propio chmod 0755 antes del self-replace, pero
            # si ese replace falla la app muestra "Downloaded to ... Open it
            # to install the new version" y sin +x el doble-clic da
            # "Permiso denegado". En .tar.xz/.zip el bit es inofensivo.
            try:
                final_path.chmod(final_path.stat().st_mode | 0o111)
            except OSError as error:
                log(f"chmod failed for {final_path}: {error}")
            log(f"downloaded {final_path}")
            if on_done:
                on_done(final_path)
        except DownloadError as error:
            if str(error) == "cancelled":
                part_path.unlink(missing_ok=True)
            else:
                log(f"download error ({url}): {error}")
            if on_error:
                on_error(str(error))
        except Exception as error:
            part_path.unlink(missing_ok=True)
            log(f"download error ({url}): {error}")
            if on_error:
                on_error(str(error))
