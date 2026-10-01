# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Day 1 spike (tests/spike_pipeline.py), onedir, no UPX.

Derived from the clearread.spec of §6.3, adapted to PyInstaller >= 6:
- removed block_cipher / cipher=: bytecode encryption was removed in PyInstaller 6.
- removed win_no_prefer_redirects / win_private_assemblies: removed in PyInstaller 6.
- console=True: the spike reports through stdout.
- no icon: resources/icons/app.ico does not exist yet.
- VC++ runtime DLLs taken from System32 (see VC_RUNTIME_DLLS below).
"""

import os

from PyInstaller.utils.hooks import collect_data_files

# PyInstaller bundles the MSVC runtime that ships with Python 3.11.9 (14.36).
# onnxruntime 1.30 needs a newer msvcp140.dll and segfaults on import with the
# old one, so the build machine's System32 copies (VC++ redistributable >= 14.40)
# replace them. App-local deployment of these DLLs is allowed by Microsoft.
SYSTEM32 = os.path.join(os.environ["SystemRoot"], "System32")
VC_RUNTIME_DLLS = ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")

# RapidOCR ships its ONNX models and config.yaml inside the package.
datas = collect_data_files("rapidocr_onnxruntime")

hiddenimports = [
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "comtypes.client",
    "pythoncom",
]

a = Analysis(
    ["tests/spike_pipeline.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "notebook", "IPython"],
    noarchive=False,
)

a.binaries = [entry for entry in a.binaries if entry[0].lower() not in VC_RUNTIME_DLLS]
a.binaries += [(name, os.path.join(SYSTEM32, name), "BINARY") for name in VC_RUNTIME_DLLS]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="spike",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="spike",
)
