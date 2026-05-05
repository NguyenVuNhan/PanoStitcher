# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PanoStitcher standalone binary."""

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
        "panostitcher",
        "panostitcher.cli",
        "panostitcher.config",
        "panostitcher.dependencies",
        "panostitcher.discovery",
        "panostitcher.metadata",
        "panostitcher.stitcher",
        "panostitcher.validator",
    ],
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
