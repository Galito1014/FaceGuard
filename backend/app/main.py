"""FaceGuard AI — punto de entrada de la aplicación (FastAPI)."""
from __future__ import annotations

import asyncio
import errno
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import config
from app.core.network import ip_allowed, parse_networks
from app.core.database import execute, query_one, run_migrations, utcnow
from app.core.security import hash_password, ws_user


def setup_logging() -> None:
    config.ensure_dirs()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.log_level, logging.INFO))
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        fh = RotatingFileHandler(config.log_dir / "faceguard.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


setup_logging()
log = logging.getLogger("faceguard")

# Los servicios se importan después de configurar el registro.
from app.api import admin, analysis, auth, camera as camera_api, dashboard, events, persons, setup  # noqa: E402
from app.services import runtime  # noqa: E402
from app.services.realtime import hub  # noqa: E402
from app.services.retention import run_retention  # noqa: E402
from app.services.settings_store import settings  # noqa: E402


def ensure_initial_admin() -> None:
    """Primer arranque: crea el superadministrador o prepara el asistente.

    Con FACEGUARD_ADMIN_PASSWORD (instalaciones automatizadas y pruebas) se crea
    el usuario "admin" como antes. Sin ella, no se crea ningún usuario: el panel
    muestra el asistente de configuración inicial (app/api/setup.py).
    """
    if query_one("SELECT id FROM users LIMIT 1"):
        return
    if not config.initial_admin_password:
        from app.services.setup import ensure_setup_code
        ensure_setup_code()
        return
    password = config.initial_admin_password
    execute("INSERT INTO users (username, full_name, password_hash, role, active, must_change_password, created_at) "
            "VALUES (?,?,?,?,1,?,?)", ("admin", "Superadministrador", hash_password(password), "superadmin",
                                  1 if config.force_password_change else 0, utcnow()))
    path = config.secret_dir / "initial_admin.txt"
    path.write_text(f"usuario: admin\ncontraseña temporal: {password}\n"
                    "Se pedirá cambiarla en el primer inicio de sesión. Borre este archivo después.\n", encoding="utf-8")
    os.chmod(path, 0o600)
    log.warning("Superadministrador inicial creado. Credenciales temporales en %s", path)


async def _status_loop() -> None:
    from app.api.dashboard import live_status
    while True:
        await asyncio.sleep(2)
        if hub.count:
            try:
                hub.publish("status", await asyncio.to_thread(live_status))
            except Exception:
                log.exception("status loop")


async def _retention_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_retention)
        except Exception:
            log.exception("retención")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    applied = run_migrations()
    if applied:
        log.info("Migraciones aplicadas: %s", applied)
    settings.load()
    ensure_initial_admin()
    hub.bind_loop(asyncio.get_running_loop())
    await asyncio.to_thread(runtime.startup)
    tasks = [asyncio.create_task(_status_loop()), asyncio.create_task(_retention_loop())]
    log.info("%s %s listo", config.app_name, config.version)
    yield
    for t in tasks:
        t.cancel()
    await asyncio.to_thread(runtime.shutdown)


app = FastAPI(title="FaceGuard AI API", version=config.version, lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")


# Redes autorizadas (ver app/core/network.py). Se lee una vez al arrancar.
ALLOWED_NETWORKS = parse_networks(config.allowed_networks)


@app.middleware("http")
async def restrict_networks(request: Request, call_next):
    host = request.client.host if request.client else None
    if not ip_allowed(host, ALLOWED_NETWORKS):
        log.warning("Conexión rechazada desde una red no autorizada: %s %s", host, request.url.path)
        return JSONResponse({"detail": "Acceso no permitido desde esta red."}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not request.url.path.startswith("/api/docs"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob: data:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:; script-src 'self'; frame-ancestors 'none'")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


for r in (auth.router, setup.router, dashboard.router, camera_api.router, persons.router, persons.photo_for_alert_router, analysis.router,
          events.router, admin.router):
    app.include_router(r)


@app.exception_handler(OSError)
async def storage_error(request: Request, exc: OSError):
    log.exception("Error de almacenamiento")
    if exc.errno == errno.ENOSPC:
        return JSONResponse({"detail": "No hay espacio de almacenamiento disponible. Libere espacio e intente de nuevo."}, 507)
    if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return JSONResponse({"detail": "Sin permisos de escritura en la carpeta de datos."}, 500)
    return JSONResponse({"detail": "Error al leer o escribir archivos."}, 500)


@app.exception_handler(sqlite3.OperationalError)
async def database_busy(request: Request, exc: sqlite3.OperationalError):
    log.exception("Error de base de datos")
    return JSONResponse({"detail": "La base de datos no está disponible en este momento. Intente de nuevo."}, 503)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": config.app_name, "version": config.version, "edition": config.edition}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    if not ip_allowed(ws.client.host if ws.client else None, ALLOWED_NETWORKS):
        await ws.close(code=4403)
        return
    user = ws_user(ws)
    if not user:
        await ws.close(code=4401)
        return
    await hub.connect(ws, user)
    try:
        while True:
            await ws.receive_text()  # mantiene la conexión; el cliente envía "ping"
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)


# --------------------------------------------- frontend compilado (archivos estáticos)
if config.frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=config.frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "No encontrado"}, status_code=404)
        file = (config.frontend_dist / path).resolve()
        if path and file.is_file() and str(file).startswith(str(config.frontend_dist.resolve())):
            return FileResponse(file)
        return FileResponse(config.frontend_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_frontend():
        return JSONResponse({"detail": "Frontend no compilado. Ejecute: cd frontend && npm install && npm run build"})
