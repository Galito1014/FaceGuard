# Guía para desarrolladores

## Arquitectura

FaceGuard AI es **un solo proyecto con un núcleo compartido** y dos formas de distribuirlo.

```
backend/      Núcleo compartido (Python + FastAPI)
  app/core/       base de datos y migraciones, seguridad y roles, cifrado, auditoría, red (network.py)
  app/services/   cámara (USB y CSI), motor facial, pipeline, alertas, GPIO, retención, respaldos,
                  asistente inicial (setup.py), actualizaciones (updates.py)
  app/api/        API REST y WebSocket
  migrations/     esquema SQLite versionado
frontend/     Panel web (React + TypeScript). Es la interfaz de ambas modalidades
desktop/      FaceGuard AI Desktop: lanzador (faceguard_desktop.py) y empaquetado (PyInstaller)
deploy/       Raspberry Pi: servicio systemd e instalador del sistema (install.sh)
installers/   windows/ (Inno Setup) · linux/ (.deb y AppImage) · raspberry-pi/ (instalador por Internet y paquete)
site/         Página de descargas (GitHub Pages)
.github/      CI, compilación de versiones y página
```

| | Desktop | Raspberry Pi |
|---|---|---|
| Arranque | `desktop/faceguard_desktop.py` inicia el núcleo en un hilo | systemd ejecuta `uvicorn app.main:app` |
| Interfaz | Ventana: WebView2 (Windows) o navegador en modo aplicación (Linux) | Navegador en la red local |
| Red | `127.0.0.1`, puerto libre, `FACEGUARD_ALLOWED_NETWORKS=loopback` | `0.0.0.0:8000`, `FACEGUARD_ALLOWED_NETWORKS=local` |
| Datos | `%LOCALAPPDATA%\FaceGuard AI` / `~/.local/share/faceguard-ai` | `/var/lib/faceguard` |
| `FACEGUARD_EDITION` | `desktop` | `pi` |

Todo lo que cambia entre plataformas se resuelve con variables de entorno y `app/core/compat.py`; el núcleo no tiene ramas de código por modalidad, salvo mostrar u ocultar opciones (p. ej. GPIO en el asistente).

## Entorno de desarrollo

```bash
# Núcleo
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.download_models        # YuNet + SFace con verificación SHA-256
python -m pytest -q                       # pruebas
python -m scripts.run                     # servidor en http://127.0.0.1:8000

# Panel (otra terminal)
cd frontend
npm ci
npm run dev                               # http://localhost:5173 con proxy a la API
npm run build                             # genera frontend/dist, que sirve el backend

# Desktop desde el código
python desktop/faceguard_desktop.py              # Windows: requiere pip install pywebview
python desktop/faceguard_desktop.py --self-test  # comprueba núcleo, panel y modelos
```

Para probar el asistente de primer uso, use una carpeta de datos vacía y no defina `FACEGUARD_ADMIN_PASSWORD`:

```bash
FACEGUARD_DATA_DIR=/tmp/fg-nuevo python -m scripts.run
```

## Empaquetar localmente

```bash
pip install -r desktop/requirements-desktop.txt
pyinstaller desktop/faceguard.spec --noconfirm --distpath build/dist --workpath build/work
build/dist/FaceGuardAI/FaceGuardAI --self-test

installers/linux/build-linux.sh 1.1.0            # Linux: .deb y AppImage en build/release
installers/raspberry-pi/build-package.sh 1.1.0   # paquete para la Pi en build/release
# Windows: iscc /DAppVersion=1.1.0 /DSourceDir=%CD%\build\dist\FaceGuardAI /DOutputDir=%CD%\build\release installers\windows\faceguard.iss
```

## Publicar una versión

1. Cambie `__version__` en `backend/app/__init__.py` y añada la sección en `CHANGELOG.md`.
2. `git tag v1.2.0 && git push origin v1.2.0`.
3. GitHub Actions (`release.yml`) prueba, compila los instaladores, prueba la instalación en ARM64 y crea un **borrador** de versión con `SHA256SUMS.txt`.
4. Revise el borrador, descargue y pruebe los instaladores en equipos reales ([validacion.md](validacion.md)) y pulse **Publish release**.
5. La página de descargas se actualiza sola.

## Migraciones

Añada `backend/migrations/NNN_descripcion.sql`. Se aplica una vez al arrancar y queda en `schema_migrations`. Nunca modifique una migración ya publicada: los usuarios que actualizan ya la tienen aplicada.

## Variables de entorno nuevas en 1.1

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `FACEGUARD_EDITION` | `server` | `desktop`, `pi` o `server` (ejecución manual) |
| `FACEGUARD_ALLOWED_NETWORKS` | `local` | `local`, `loopback`, `all` o lista de CIDR |
| `FACEGUARD_UPDATE_REPO` | `Galito1014/FaceGuard` | Repositorio donde se buscan versiones nuevas |
| `FACEGUARD_CAMERA_BACKEND` | `auto` | Añade `picamera2` para cámaras CSI |
| `FACEGUARD_LOGIN_MAX_ATTEMPTS` | `5` (antes `0`) | Intentos fallidos antes de esperar; `0` = ilimitados |
