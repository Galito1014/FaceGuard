# Componentes de terceros

FaceGuard AI se distribuye bajo la licencia Apache 2.0 (ver [LICENSE](LICENSE)). Los instaladores incluyen los siguientes componentes de terceros, cada uno bajo su propia licencia. Las versiones exactas de cada publicación están fijadas en `backend/requirements.txt`, `desktop/requirements-desktop.txt` y `frontend/package-lock.json`.

## Modelos de inteligencia artificial

| Componente | Licencia | Origen |
|---|---|---|
| YuNet — `face_detection_yunet_2023mar.onnx` | Apache 2.0 | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| SFace — `face_recognition_sface_2021dec.onnx` | Apache 2.0 | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) |

Los modelos se usan sin modificar.

## Núcleo (Python)

| Componente | Licencia |
|---|---|
| OpenCV (`opencv-python-headless`) | Apache 2.0. Las ruedas incluyen FFmpeg (LGPL 2.1) y otras bibliotecas listadas en el propio paquete |
| NumPy | BSD-3-Clause (y licencias de sus componentes) |
| FastAPI | MIT |
| Starlette | BSD-3-Clause |
| Uvicorn | BSD-3-Clause |
| Pydantic / pydantic-core | MIT |
| python-multipart | Apache 2.0 |
| cryptography | Apache 2.0 o BSD-3-Clause |
| psutil | BSD-3-Clause |
| ReportLab | BSD |
| websockets, httptools, h11, anyio, click, PyYAML, watchfiles, python-dotenv | MIT / BSD |
| gpiozero (solo Raspberry Pi) | BSD-3-Clause |
| picamera2 (solo Raspberry Pi con cámara CSI, desde apt) | BSD-2-Clause |

## FaceGuard AI Desktop

| Componente | Licencia |
|---|---|
| Python (intérprete incluido por PyInstaller) | PSF License |
| PyInstaller (cargador) | GPL 2.0 con excepción para el cargador: permite distribuir programas empaquetados con cualquier licencia |
| pywebview (solo Windows) | BSD-3-Clause |
| pythonnet / clr_loader (solo Windows) | MIT |
| Microsoft Edge WebView2 Runtime | Componente de Windows; no se incluye en el instalador |
| Tcl/Tk (ventana de control) | Licencia Tcl/Tk (tipo BSD) |

## Panel web (frontend)

| Componente | Licencia |
|---|---|
| React, React DOM, React Router | MIT |
| TanStack Query | MIT |
| Recharts | MIT |
| Lucide | ISC |
| Tailwind CSS | MIT |
| clsx | MIT |
| Inter y JetBrains Mono (Fontsource) | SIL Open Font License 1.1 |

## Herramientas de compilación (no se incluyen en los instaladores)

Vite, TypeScript, PostCSS, Autoprefixer (MIT), Inno Setup (licencia de Inno Setup) y appimagetool (MIT).
