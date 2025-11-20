# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# --- PyQt6 ---
pyqt6_data = collect_data_files("PyQt6")
pyqt6_mods = collect_submodules("PyQt6")

# --- Requests (сертифікати та CA bundle) ---
requests_data = collect_data_files("requests")

# Збираємо всі модуля програми
hidden = []
hidden += pyqt6_mods
hidden += collect_submodules("requests")
hidden += collect_submodules("asyncio")

datas=[
    ('icon.ico', '.'),
    ('telegram.ico', '.'),
    ('lighttheme.ico', '.'),
    ('darktheme.ico', '.'),
]
datas += pyqt6_data
datas += requests_data

a = Analysis(
    ['PingMonitor.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
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
    name='PingMonitor',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico'
)
