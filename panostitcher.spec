# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PanoStitcher standalone binary."""

a = Analysis(
    ["src/panostitcher/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["panostitcher"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="panostitcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
