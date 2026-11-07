"""FaceGuard AI Desktop — lanzador de escritorio para Windows y Linux.

Arranca el mismo núcleo (backend FastAPI) que usa la Raspberry Pi, pero:

* solo escucha en 127.0.0.1, en un puerto libre elegido al azar;
* acepta conexiones únicamente desde este equipo (FACEGUARD_ALLOWED_NETWORKS=loopback);
* guarda los datos en la carpeta del usuario, fuera de la carpeta del programa,
  para que actualizar o reinstalar no borre personas, historial ni configuración:
    Windows: %LOCALAPPDATA%\\FaceGuard AI
    Linux:   $XDG_DATA_HOME/faceguard-ai  (normalmente ~/.local/share/faceguard-ai)
* muestra el panel en una ventana propia:
    Windows: ventana nativa con pywebview + WebView2 (incluido en Windows 10/11);
    Linux:   ventana de aplicación de Chromium, Google Chrome, Edge o Brave
             (modo --app, sin barra de direcciones), si hay alguno instalado.

Si no se puede crear esa ventana, abre el panel en el navegador predeterminado
y muestra una pequeña ventana de control para cerrar FaceGuard AI.

Uso para desarrollo (desde la raíz del repositorio):
    python desktop/faceguard_desktop.py              # ventana de escritorio
    python desktop/faceguard_desktop.py --browser    # abre el navegador
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_TITLE = "FaceGuard AI"
FROZEN = getattr(sys, "frozen", False)


def resource_root() -> Path:
    """Carpeta con el código y los recursos (en el instalador o en el repositorio)."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent / "backend"


def user_data_dir() -> Path:
    override = os.getenv("FACEGUARD_DATA_DIR")
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override)))
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "FaceGuard AI"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FaceGuard AI"
    base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "faceguard-ai"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SingleInstance:
    """Impide abrir dos copias a la vez (compartirían la cámara y la base de datos)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        # msvcrt bloquea desde la posición actual: se bloquea un byte lejos del puerto
        # guardado, para que otra copia pueda leerlo y abrir la ventana existente.
        self.fh.seek(4096)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def write_port(self, port: int) -> None:
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(str(port))
        self.fh.flush()

    def existing_port(self) -> int | None:
        try:
            return int(self.path.read_text().strip())
        except (OSError, ValueError):
            return None


def configure_environment(data_dir: Path) -> None:
    root = resource_root()
    env = {
        "FACEGUARD_EDITION": "desktop",
        "FACEGUARD_DATA_DIR": str(data_dir / "data"),
        "FACEGUARD_HOST": "127.0.0.1",
        "FACEGUARD_ALLOWED_NETWORKS": "loopback",
        # Archivo opcional para ajustes avanzados del usuario (no se sobrescribe al actualizar).
        "FACEGUARD_ENV_FILE": str(data_dir / "faceguard.env"),
    }
    if FROZEN:
        env["FACEGUARD_MODELS_DIR"] = str(root / "models")
        env["FACEGUARD_FRONTEND_DIST"] = str(root / "frontend_dist")
    for k, v in env.items():
        os.environ.setdefault(k, v)
    if not FROZEN:
        sys.path.insert(0, str(root))


def start_server(port: int):
    import uvicorn

    from app.main import app  # importa después de fijar las variables de entorno

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, workers=1, log_level="warning",
                         access_log=False, log_config=None)
    server = uvicorn.Server(cfg)
    thread = threading.Thread(target=server.run, name="faceguard-server", daemon=True)
    thread.start()
    return server, thread


def wait_ready(url: str, timeout: float = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def show_error(message: str) -> None:
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def run_window(url: str) -> bool:
    """Ventana nativa. Devuelve False si pywebview no está disponible en este equipo."""
    try:
        import webview
    except Exception as exc:
        logging.getLogger("faceguard.desktop").warning("pywebview no disponible: %s", exc)
        return False
    try:
        webview.create_window(APP_TITLE, url, width=1360, height=860, min_size=(960, 640), text_select=True)
        webview.start(private_mode=False)
        return True
    except Exception as exc:
        logging.getLogger("faceguard.desktop").warning("No se pudo abrir la ventana nativa: %s", exc)
        return False


APP_BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge",
                "microsoft-edge-stable", "brave-browser")


def run_app_browser(url: str, profile_dir: Path) -> bool:
    """Linux: abre el panel como ventana de aplicación y espera a que se cierre."""
    import shutil
    import subprocess
    for name in APP_BROWSERS:
        exe = shutil.which(name)
        if not exe:
            continue
        # Un perfil propio hace que el navegador sea un proceso independiente que
        # termina al cerrar la ventana (así sabemos cuándo cerrar FaceGuard AI).
        cmd = [exe, f"--app={url}", f"--user-data-dir={profile_dir}", "--no-first-run",
               "--no-default-browser-check", "--class=FaceGuardAI", "--window-size=1360,860"]
        try:
            subprocess.run(cmd, check=False)
            return True
        except OSError:
            continue
    return False


def run_browser_fallback(url: str) -> None:
    """Abre el navegador y deja una ventana pequeña para cerrar FaceGuard AI."""
    webbrowser.open(url)
    try:
        import tkinter
        from tkinter import ttk
    except Exception:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    root = tkinter.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.grid()
    ttk.Label(frm, text="FaceGuard AI está en ejecución.").grid(column=0, row=0, columnspan=2, pady=(0, 8))
    ttk.Button(frm, text="Abrir panel", command=lambda: webbrowser.open(url)).grid(column=0, row=1, padx=4)
    ttk.Button(frm, text="Cerrar FaceGuard AI", command=root.destroy).grid(column=1, row=1, padx=4)
    root.mainloop()


def self_test(data_dir: Path | None) -> int:
    """Prueba sin ventana: el paquete arranca, sirve el panel y carga los modelos."""
    import tempfile
    tmp = None
    if data_dir is None:
        tmp = tempfile.TemporaryDirectory(prefix="faceguard-selftest-")
        data_dir = Path(tmp.name)
    os.environ.setdefault("FACEGUARD_DISABLE_WORKERS", "1")  # sin cámara en CI
    configure_environment(data_dir)
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server, thread = start_server(port)
    problems = []
    try:
        if not wait_ready(url, timeout=90):
            problems.append("el servidor no respondió")
        else:
            with urllib.request.urlopen(url + "/", timeout=5) as r:
                if r.status != 200 or b'id="root"' not in r.read():
                    problems.append("el panel web no se sirvió")
            from app.services.face_engine import engine
            if not engine.ready:
                problems.append(f"motor facial no cargado: {engine.error}")
            with urllib.request.urlopen(url + "/api/setup/status", timeout=5) as r:
                if b"needs_setup" not in r.read():
                    problems.append("API de configuración inicial no disponible")
    except Exception as exc:
        problems.append(f"{exc.__class__.__name__}: {exc}")
    finally:
        server.should_exit = True
        thread.join(timeout=15)
    if problems:
        print("AUTOPRUEBA FALLIDA: " + "; ".join(problems))
        return 1
    print("AUTOPRUEBA CORRECTA: núcleo, panel web, base de datos y modelos listos")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FaceGuard AI Desktop")
    parser.add_argument("--browser", action="store_true", help="Abrir en el navegador en vez de la ventana nativa")
    parser.add_argument("--data-dir", help="Carpeta de datos (por defecto, la del usuario)")
    parser.add_argument("--self-test", action="store_true",
                        help="Arranca el núcleo, comprueba panel, base de datos y modelos, y sale (para CI)")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(Path(args.data_dir) if args.data_dir else None)

    data_dir = Path(args.data_dir) if args.data_dir else user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    lock = SingleInstance(data_dir / "faceguard.lock")
    if not lock.acquire():
        port = lock.existing_port()
        if port:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        else:
            show_error("FaceGuard AI ya está abierto.")
        return 0

    configure_environment(data_dir)
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    try:
        server, thread = start_server(port)
    except Exception as exc:
        show_error(f"No se pudo iniciar FaceGuard AI:\n{exc}\n\nRevise el registro en {data_dir / 'data' / 'logs'}")
        return 1
    if not wait_ready(url):
        show_error(f"FaceGuard AI no respondió a tiempo.\nRevise el registro en {data_dir / 'data' / 'logs'}")
        server.should_exit = True
        return 1
    lock.write_port(port)

    if args.browser:
        run_browser_fallback(url)
    elif sys.platform == "win32":
        if not run_window(url):
            run_browser_fallback(url)
    elif not run_app_browser(url, data_dir / "ventana"):
        run_browser_fallback(url)

    server.should_exit = True  # libera la cámara y cierra la base de datos
    thread.join(timeout=15)
    return 0


if __name__ == "__main__":
    if FROZEN:
        import multiprocessing
        multiprocessing.freeze_support()
    raise SystemExit(main())
