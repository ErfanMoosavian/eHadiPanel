# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(SPECPATH)
def _p(*parts): return os.path.join(ROOT, *parts)

datas = [
    (_p('src', 'ui', 'web'), 'src/ui/web'),
    (_p('src'), 'src'),
    (_p('assets', 'fonts'), 'assets/fonts'),
    (_p('assets', 'logo.png'), 'assets'),
    (_p('build', 'splash_logo.png'), 'build'),
    (_p('build', 'splash_runner.py'), 'build'),
    (_p('build', 'eHadiPanel.ico'), 'build'),
]
binaries = []
hiddenimports = [
    'webview', 'clr', 'pythonnet', 'bottle', 'proxy_tools',
    'duckdb', 'lancedb', 'pyarrow', 'pandas', 'numpy', 'openpyxl',
    'docx', 'pptx', 'fitz', 'pymupdf', 'PIL', 'PIL._tkinter_finder',
    'tkinter', 'google.genai', 'pydantic', 'faster_whisper',
    'ctranslate2', 'sounddevice', 'sqlite3', 'json', 'csv', 'ctypes',
]
for _pkg in ('webview', 'duckdb', 'lancedb', 'pyarrow', 'docx'):
    tmp_ret = collect_all(_pkg)
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

a = Analysis([_p('main.py')], pathex=[_p('build')], binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='eHadiPanel', debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False, disable_windowed_traceback=False, argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None, icon=[_p('build', 'eHadiPanel.ico')])
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='eHadiPanel')
