# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: empaqueta FaceGuard AI Desktop (Windows y Linux) en una carpeta "onedir".
# Uso (desde la raíz del repositorio, con los modelos descargados y el frontend compilado):
#   pyinstaller desktop/faceguard.spec --noconfirm --distpath build/dist --workpath build/work
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"
ICON = ROOT / "installers" / "assets" / ("faceguard.ico" if sys.platform == "win32" else "faceguard.png")

for required in (BACKEND / "models" / "face_detection_yunet_2023mar.onnx",
                 BACKEND / "models" / "face_recognition_sface_2021dec.onnx",
                 ROOT / "frontend" / "dist" / "index.html"):
    if not required.exists():
        raise SystemExit(f"Falta {required}. Descargue los modelos y compile el frontend antes de empaquetar.")

datas = [
    (str(BACKEND / "migrations"), "migrations"),
    (str(BACKEND / "models"), "models"),
    (str(ROOT / "frontend" / "dist"), "frontend_dist"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
datas += collect_data_files("reportlab")

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + ["multipart", "python_multipart"]
    + (collect_submodules("webview") if sys.platform == "win32" else [])
)

a = Analysis(
    [str(ROOT / "desktop" / "faceguard_desktop.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["gpiozero", "lgpio", "pytest", "tkinter.test", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FaceGuardAI",
    console=False,
    icon=str(ICON) if ICON.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="FaceGuardAI")
