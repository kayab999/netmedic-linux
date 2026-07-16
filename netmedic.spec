# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

import os

REPO_ROOT = os.path.dirname(os.path.abspath(SPEC))

datas = [
    (os.path.join(REPO_ROOT, 'assets', 'netmedic.png'), 'assets'),
    (os.path.join(REPO_ROOT, 'docs', 'MANUAL.md'), 'docs'),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all('netmedic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret_gi = collect_all('gi')
datas += tmp_ret_gi[0]; binaries += tmp_ret_gi[1]; hiddenimports += tmp_ret_gi[2]


a = Analysis(
    ['netmedic/netmedic/app.py'],
    pathex=['netmedic'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['netmedic_ai'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='netmedic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
