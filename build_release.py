"""
اسکریپت ساخت بسته نصب و انتشار نسخه Beta 0.2 سامانه eHadiPanel
مؤسسه علمی فرهنگی امام هادی علیه‌السلام
- بدون هیچ اثر از v20 یا Enterprise
- بسته‌بندی کامل فایل‌های وب، اسپلش اسکرین جدید eHP و فونت‌های Vazirmatn
- تولید خودکار فایل Setup.exe با Inno Setup یا بسته کامل آماده نصب در صورت نبود Inno Setup
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
APP_NAME = "eHadiPanel"
APP_VER = "0.2.0-beta"
RELEASE_TAG = "Beta 0.2"


def run(cmd, check=True):
    print(">>", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, cwd=str(ROOT), check=check)


def ensure_build_deps():
    for pkg, mod in (("pyinstaller", "PyInstaller"), ("pillow", "PIL")):
        res = subprocess.run([PY, "-c", f"import {mod}"], capture_output=True)
        if res.returncode != 0:
            print(f"[INFO] Installing {pkg} in venv...", flush=True)
            run([PY, "-m", "pip", "install", "--quiet", pkg])


def patch_frozen_paths():
    main_py = ROOT / "main.py"
    if not main_py.exists():
        raise FileNotFoundError("main.py not found in project root.")
    txt = main_py.read_text(encoding="utf-8")
    if "_EHADI_FROZEN_PATCHED" in txt:
        return
    bootstrap = (
        "# _EHADI_FROZEN_PATCHED\n"
        "import os as _os, sys as _sys\n"
        "from pathlib import Path as _Path\n"
        "if getattr(_sys, 'frozen', False):\n"
        "    _APP_DIR = _Path(_sys.executable).resolve().parent\n"
        "    _os.chdir(str(_APP_DIR))\n"
        "    _os.environ['EHADI_BUNDLE_DIR'] = str(_Path(getattr(_sys, '_MEIPASS', _APP_DIR)))\n"
        "    _os.environ['EHADI_APP_DIR'] = str(_APP_DIR)\n\n"
    )
    txt = bootstrap + txt
    txt = re.sub(
        r'(["\'])src[/\\]+ui[/\\]+web\1',
        r'(str(_Path(getattr(_sys, "_MEIPASS", ".")) / "src" / "ui" / "web") if getattr(_sys, "frozen", False) else "src/ui/web")',
        txt,
    )
    main_py.write_text(txt, encoding="utf-8")
    print("[OK] Patched main.py for frozen executable path resolution.", flush=True)


def build_windows_icon() -> Path | None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    ico_path = BUILD_DIR / "eHadiPanel.ico"
    if ico_path.exists():
        return ico_path
    web_dir = ROOT / "src" / "ui" / "web"
    candidates = list(web_dir.rglob("*.png")) + list(web_dir.rglob("*.jpg")) + list(web_dir.rglob("*.webp"))
    logo_file = next((c for c in candidates if "logo" in c.name.lower()), candidates[0] if candidates else None)
    if not logo_file:
        return None
    try:
        from PIL import Image

        img = Image.open(logo_file).convert("RGBA")
        side = max(img.width, img.height, 256)
        canvas = Image.new("RGBA", (side, side), (4, 9, 22, 255))
        pad = int(side * 0.14)
        img.thumbnail((side - pad * 2, side - pad * 2), Image.LANCZOS)
        x = (side - img.width) // 2
        y = (side - img.height) // 2
        canvas.paste(img, (x, y), img)
        canvas.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"[OK] Generated crisp multi-size icon: {ico_path}", flush=True)
        return ico_path
    except Exception as e:
        print(f"[WARN] Could not generate .ico ({e}); continuing without custom icon.", flush=True)
        return None


def detect_hidden_imports():
    candidates = [
        "webview", "clr", "pythonnet", "bottle", "proxy_tools",
        "duckdb", "lancedb", "pyarrow", "pandas", "numpy",
        "openpyxl", "docx", "reportlab", "arabic_reshaper", "bidi",
        "PIL", "PIL._tkinter_finder", "tkinter", "google.genai",
        "pydantic", "httpx", "faster_whisper", "ctranslate2",
        "sounddevice", "scipy", "sqlite3", "json", "csv", "ctypes",
    ]
    found = []
    for mod in candidates:
        r = subprocess.run([PY, "-c", f"import {mod}"], capture_output=True)
        if r.returncode == 0:
            found.append(mod)
    return found


FAST_MODE = any(a in ("--fast", "-f") for a in sys.argv[1:])


def compile_pyinstaller(ico_path: Path | None):
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    hidden = detect_hidden_imports()
    cmd = [
        PY, "-m", "PyInstaller",
        "--noconfirm",
        *([] if FAST_MODE else ["--clean"]),
        "--windowed",
        "--onedir",
        "--name", APP_NAME,
        "--add-data", f"{ROOT / 'src' / 'ui' / 'web'};src/ui/web",
        "--add-data", f"{ROOT / 'src'};src",
    ]
    fonts_dir = ROOT / "assets" / "fonts"
    if fonts_dir.exists():
        cmd += ["--add-data", f"{fonts_dir};assets/fonts"]
    logo_png = ROOT / "assets" / "logo.png"
    if logo_png.exists():
        cmd += ["--add-data", f"{logo_png};assets"]
    splash_hp = BUILD_DIR / "splash_hp_badge.png"
    if splash_hp.exists():
        cmd += ["--add-data", f"{splash_hp};build"]
    splash_logo = BUILD_DIR / "splash_logo.png"
    if splash_logo.exists():
        cmd += ["--add-data", f"{splash_logo};build"]
    splash_py = BUILD_DIR / "splash_runner.py"
    if splash_py.exists():
        cmd += ["--add-data", f"{splash_py};build", "--paths", str(BUILD_DIR)]
    if ico_path and ico_path.exists():
        cmd += ["--icon", str(ico_path), "--add-data", f"{ico_path};build"]
    for h in hidden:
        cmd += ["--hidden-import", h]
    for pkg in ("webview", "duckdb", "lancedb", "pyarrow", "arabic_reshaper", "bidi", "reportlab", "docx"):
        if pkg in hidden:
            cmd += ["--collect-all", pkg]
    cmd.append(str(ROOT / "main.py"))
    run(cmd)


def create_installer_or_package(ico_path: Path | None):
    app_out = DIST_DIR / APP_NAME
    if not app_out.exists():
        raise RuntimeError("PyInstaller output folder not found!")

    # Clean writable data/logs/backups folders for first-time manager installation
    for sub in ("data/raw_docs", "data/duckdb", "data/lancedb", "data/storage", "backups", "logs"):
        (app_out / sub).mkdir(parents=True, exist_ok=True)

    splash_hp_src = BUILD_DIR / "splash_hp_badge.png"
    if splash_hp_src.exists():
        shp_dst = app_out / "build" / "splash_hp_badge.png"
        shp_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(splash_hp_src, shp_dst)
    splash_logo_src = BUILD_DIR / "splash_logo.png"
    if splash_logo_src.exists():
        sl_dst = app_out / "build" / "splash_logo.png"
        sl_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(splash_logo_src, sl_dst)
    splash_src = BUILD_DIR / "splash_runner.py"
    if splash_src.exists():
        sp_dst = app_out / "build" / "splash_runner.py"
        sp_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(splash_src, sp_dst)

    # Ensure assets/logo.png is present directly inside dist/eHadiPanel/assets/logo.png
    logo_src = ROOT / "assets" / "logo.png"
    if logo_src.exists():
        logo_dst = app_out / "assets" / "logo.png"
        logo_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(logo_src, logo_dst)

    # Copy bundled Vazirmatn fonts next to app so installer can register them on manager PC
    fonts_src = ROOT / "assets" / "fonts"
    fonts_dst = app_out / "assets" / "fonts"
    if fonts_src.exists():
        fonts_dst.mkdir(parents=True, exist_ok=True)
        for fp in fonts_src.iterdir():
            if fp.is_file():
                shutil.copy2(fp, fonts_dst / fp.name)

    # Ensure build/eHadiPanel.ico is copied into dist/eHadiPanel/build/eHadiPanel.ico
    if ico_path and ico_path.exists():
        dist_ico = app_out / "build" / "eHadiPanel.ico"
        dist_ico.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ico_path, dist_ico)

    # Generate clean Beta 0.2 Inno Setup script (.iss)
    iss_path = BUILD_DIR / "eHadiPanel_Beta_0.2_Installer.iss"
    font_entries = []
    if fonts_dst.exists():
        for fp in sorted(fonts_dst.iterdir()):
            if fp.is_file() and fp.suffix.lower() in {".ttf", ".otf"}:
                font_entries.append(
                    f'Source: "{app_out}\\assets\\fonts\\{fp.name}"; DestDir: "{{autofonts}}"; FontInstall: "{fp.stem}"; Flags: onlyifdoesntexist uninsneveruninstall'
                )
    font_lines_str = "\n".join(font_entries)
    icon_setup_line = f'SetupIconFile="{ico_path}"' if ico_path and ico_path.exists() else ""

    iss_content = (
        "[Setup]\n"
        "AppId={{8E4A7B12-9C3D-4F21-A812-E4AD19002026}}\n"
        f"AppName=eHadiPanel {RELEASE_TAG}\n"
        f"AppVersion={APP_VER}\n"
        "AppPublisher=Imam Hadi (AS) Cultural & Scientific Institute\n"
        "DefaultDirName={autopf}\\eHadiPanel\n"
        f"DefaultGroupName=eHadiPanel {RELEASE_TAG}\n"
        "AllowNoIcons=yes\n"
        f"OutputDir={DIST_DIR}\n"
        "OutputBaseFilename=eHadiPanel_Beta_0.2_Setup\n"
        + ("Compression=lzma2/fast\nSolidCompression=no\n" if FAST_MODE else "Compression=lzma2/ultra64\nSolidCompression=yes\n")
        + "WizardStyle=modern\n"
        "PrivilegesRequired=lowest\n"
        + (f"{icon_setup_line}\n" if icon_setup_line else "")
        + "\n"
        "[Tasks]\n"
        'Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"\n'
        "\n"
        "[Files]\n"
        f'Source: "{app_out}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs\n'
        + (f"{font_lines_str}\n" if font_lines_str else "")
        + "\n"
        "[Icons]\n"
        f'Name: "{{group}}\\eHadiPanel {RELEASE_TAG}"; Filename: "{{app}}\\{APP_NAME}.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\build\\eHadiPanel.ico"\n'
        f'Name: "{{autodesktop}}\\eHadiPanel {RELEASE_TAG}"; Filename: "{{app}}\\{APP_NAME}.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\build\\eHadiPanel.ico"; Tasks: desktopicon\n'
        "\n"
        "[Run]\n"
        f'Filename: "{{app}}\\{APP_NAME}.exe"; Description: "Launch eHadiPanel {RELEASE_TAG}"; Flags: nowait postinstall skipifsilent\n'
    )
    iss_path.write_text(iss_content, encoding="utf-8")

    iscc_candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    iscc = next((p for p in iscc_candidates if p.exists()), None)

    if iscc:
        print(f"[INFO] Inno Setup found! Building eHadiPanel_Beta_0.2_Setup.exe (mode={'FAST' if FAST_MODE else 'ULTRA'})...", flush=True)
        run([str(iscc), str(iss_path)])
        print(f"\n[SUCCESS] Windows Setup created: {DIST_DIR / 'eHadiPanel_Beta_0.2_Setup.exe'}", flush=True)
    else:
        zip_path = DIST_DIR / "eHadiPanel_Beta_0.2_Install_Package.zip"
        print("[INFO] Inno Setup not installed; creating clean Beta 0.2 installation package...", flush=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in app_out.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(DIST_DIR))
        print(f"\n[SUCCESS] App folder ready: {app_out / (APP_NAME + '.exe')}", flush=True)
        print(f"[SUCCESS] Clean Install Archive ready: {zip_path}", flush=True)
        print(f"[INFO] Inno Setup script saved at: {iss_path}", flush=True)


if __name__ == "__main__":
    ensure_build_deps()
    patch_frozen_paths()
    ico = build_windows_icon()
    compile_pyinstaller(ico)
    create_installer_or_package(ico)
