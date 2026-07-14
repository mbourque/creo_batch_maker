# -*- mode: python ; coding: utf-8 -*-
# Put main.exe in the project folder (next to kill.bat), not under ./dist.
#
# PyInstaller 6: EXE() builds the one-file exe at os.path.join(CONF['distpath'], name + '.exe').
# Assigning global DISTPATH in this file does NOT change CONF — that is why output stayed in dist/.
import os

from PyInstaller.config import CONF

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
CONF['distpath'] = _SPEC_DIR
CONF['workpath'] = os.path.join(_SPEC_DIR, 'build', CONF['specnm'])
os.makedirs(CONF['distpath'], exist_ok=True)
os.makedirs(CONF['workpath'], exist_ok=True)

# Sidecar files (model_checks.xml, report_template.html.j2, kill.bat, purge_cache.ps1, configs\) are NOT
# embedded here — they must sit next to main.exe at runtime (see _app_bundle_dir in main.py).

_APP_MODULES = [
    'build_errors_warnings_report',
    'merge_master_xml',
    'patch',
    'make_html_summary',
    'make_html_statistics',
    'update_start_from_xml',
]

a = Analysis(
    ['main.py'],
    pathex=[_SPEC_DIR],
    binaries=[],
    datas=[],
    hiddenimports=_APP_MODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='main',
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
