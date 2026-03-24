# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

# 1. Recolectar módulos de introspección (GI) de forma exhaustiva
# Esto soluciona el error "Namespace GIRepository not available"
hidden_imports = collect_submodules('gi') + [
    'gi.repository.Gtk', 
    'gi.repository.Gdk', 
    'gi.repository.GLib', 
    'gi.repository.GObject',
    'gi.repository.Gio',
    'gi.repository.Pango',
    'gi.repository.Atk',
    'gi.repository.GdkPixbuf'
]

# 2. Recolectar datos y bibliotecas dinámicas necesarias
datas = [
    ('netmedic.png', '.'),
    ('netmedic/netmedic/operators', 'netmedic/operators'),
    ('docs', 'docs'),
    ('CHANGELOG.md', '.'),
    ('RELEASE_NOTES.md', '.'),
]

# Forzar la inclusión de los typelibs del sistema
# Buscamos la ruta real en Debian/Ubuntu/Arch
lib_paths = ['/usr/lib/x86_64-linux-gnu', '/usr/lib', '/usr/lib64']
typelib_path = None
for p in lib_paths:
    test_path = os.path.join(p, 'girepository-1.0')
    if os.path.exists(test_path):
        typelib_path = test_path
        datas.append((test_path, 'gi_typelibs'))
        break

a = Analysis(
    ['netmedic/netmedic/app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 3. Hook de ejecución para corregir el PATH de Typelibs en caliente
with open('pyi_gi_runtime_hook.py', 'w') as f:
    f.write("import os, sys, gi\n")
    f.write("bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath('.'))\n")
    f.write("typelib_path = os.path.join(bundle_dir, 'gi_typelibs')\n")
    f.write("if os.path.exists(typelib_path):\n")
    f.write("    os.environ['GI_TYPELIB_PATH'] = typelib_path\n")
    # Limpieza de LD_LIBRARY_PATH para evitar conflictos con drivers del sistema
    f.write("if 'LD_LIBRARY_PATH' in os.environ:\n")
    f.write("    del os.environ['LD_LIBRARY_PATH']\n")

a.runtime_hooks = ['pyi_gi_runtime_hook.py']

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='netmedic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False, 
    icon='netmedic.png'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    name='netmedic_bundle'
)
