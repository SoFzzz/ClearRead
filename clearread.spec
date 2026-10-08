# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for ClearRead Desktop (Windows onedir, no UPX).

Derived from spike.spec and §6.3; validated against PyInstaller >= 6.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

# PyInstaller bundles the MSVC runtime that ships with Python 3.11.9 (14.36).
# onnxruntime 1.30 needs a newer msvcp140.dll and segfaults on import with the
# old one, so the build machine's System32 copies (VC++ redistributable >= 14.40)
# replace them. App-local deployment of these DLLs is allowed by Microsoft.
SYSTEM32 = os.path.join(os.environ["SystemRoot"], "System32")
VC_RUNTIME_DLLS = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
UNUSED_BINARY_PREFIX = "opencv_videoio_ffmpeg"

CLIENT_TOKEN_FILE = os.path.join("resources", "client_token.local.json")
if not os.path.isfile(CLIENT_TOKEN_FILE):
    raise SystemExit(
        f"BUILD ABORTED: {CLIENT_TOKEN_FILE} is missing. Create it with "
        '{"client_token": "<CLIENT_TOKEN of the Render backend>"} before building; '
        "without it the .exe could never use the AI assistant."
    )

datas = [
    ("resources/fonts", "resources/fonts"),
    ("resources/models", "resources/models"),
    ("resources/icons", "resources/icons"),
    ("resources/samples", "resources/samples"),
    (CLIENT_TOKEN_FILE, "resources"),
]
# RapidOCR ships its ONNX models and config.yaml inside the package.
datas += collect_data_files("rapidocr_onnxruntime")
# silabeador reads its exceptions.lst from disk on every call.
datas += collect_data_files("silabeador")

hiddenimports = [
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "comtypes.client",
    "pythoncom",
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
]

UNUSED_QT_MODULES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtTextToSpeech",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
]

a = Analysis(
    ["src/clearread/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        "PySide6": {
            "plugins": ["platforms", "styles", "imageformats", "iconengines", "networkinformation"]
        }
    },
    runtime_hooks=[],
    excludes=["fastapi", "uvicorn", "starlette", "tkinter", "matplotlib", "scipy", "notebook", "IPython"]
    + UNUSED_QT_MODULES,
    noarchive=False,
)

a.binaries = [
    entry
    for entry in a.binaries
    if entry[0].lower() not in VC_RUNTIME_DLLS
    and not os.path.basename(entry[0]).startswith(UNUSED_BINARY_PREFIX)
]
a.binaries += [(name, os.path.join(SYSTEM32, name), "BINARY") for name in VC_RUNTIME_DLLS]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClearRead",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/icons/app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ClearRead",
)
