# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置模板。"""
import pathlib

from PyInstaller.utils.hooks import collect_submodules

project_root = pathlib.Path(__file__).resolve().parent.parent

a = Analysis(
    ['autowriter_desktop/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(project_root / 'autowriter_desktop' / 'assets'), 'assets')],
    hiddenimports=collect_submodules('autowriter_desktop'),
    hookspath=[],
    hooksconfig={},
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoWriter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AutoWriter'
)
