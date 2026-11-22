# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:/Users/erfan/Desktop/eHadiPanel/src/ui/web', 'src/ui/web'), ('C:/Users/erfan/Desktop/eHadiPanel/src', 'src'), ('C:/Users/erfan/Desktop/eHadiPanel/assets/fonts', 'assets/fonts'), ('C:/Users/erfan/Desktop/eHadiPanel/assets/logo.png', 'assets'), ('C:/Users/erfan/Desktop/eHadiPanel/build/splash_hp_badge.png', 'build'), ('C:/Users/erfan/Desktop/eHadiPanel/build/splash_runner.py', 'build'), ('C:/Users/erfan/Desktop/eHadiPanel/build/eHadiPanel.ico', 'build')]
binaries = []
hiddenimports = ['webview', 'clr', 'pythonnet', 'bottle', 'proxy_tools', 'duckdb', 'lancedb', 'pyarrow', 'pandas', 'numpy', 'openpyxl', 'docx', 'PIL', 'PIL._tkinter_finder', 'tkinter', 'google.genai', 'pydantic', 'faster_whisper', 'ctranslate2', 'sounddevice', 'sqlite3', 'json', 'csv', 'ctypes']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('duckdb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('lancedb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyarrow')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('docx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Users/erfan/Desktop/eHadiPanel/main.py'],
    pathex=['C:/Users/erfan/Desktop/eHadiPanel/build'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='eHadiPanel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/erfan/Desktop/eHadiPanel/build/eHadiPanel.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='eHadiPanel',
)
