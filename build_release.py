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
APP_VER = "20.0.0"

def run(cmd, check=True):
    print(">>", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, cwd=str(ROOT), check=check)

def ensure_build_deps():
    for pkg in ("pyinstaller", "pillow"):
        res = subprocess.run([PY, "-c", f"import {pkg.replace('pillow', 'PIL').replace('pyinstaller', 'PyInstaller')}"], capture_output=True)
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
    shutil.copy2(main_py, ROOT / "main.py.bak_v20")
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
    # Redirect src/ui/web lookups to _MEIPASS when running as compiled exe
    txt = re.sub(
        r'(["\'])src[/\\]+ui[/\\]+web\1',
        r'(str(_Path(getattr(_sys, "_MEIPASS", ".")) / "src" / "ui" / "web") if getattr(_sys, "frozen", False) else "src/ui/web")',
        txt
    )
    main_py.write_text(txt, encoding="utf-8")
    print("[OK] Patched main.py for frozen executable path resolution.", flush=True)

def build_windows_icon() -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    ico_path = BUILD_DIR / "eHadiPanel.ico"
    web_dir = ROOT / "src" / "ui" / "web"
    candidates = list(web_dir.rglob("*.png")) + list(web_dir.rglob("*.jpg")) + list(web_dir.rglob("*.webp"))
    logo_file = next((c for c in candidates if "logo" in c.name.lower()), candidates[0] if candidates else None)
    if not logo_file:
        return None
    try:
        from PIL import Image
        img = Image.open(logo_file).convert("RGBA")
        side = max(img.width, img.height, 256)
        canvas = Image.new("RGBA", (side, side), (10, 18, 34, 255))
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
        "PIL", "google.genai", "pydantic", "httpx",
        "faster_whisper", "ctranslate2", "sounddevice", "scipy",
        "sqlite3", "json", "csv", "ctypes"
    ]
    found = []
    for mod in candidates:
        r = subprocess.run([PY, "-c", f"import {mod}"], capture_output=True)
        if r.returncode == 0:
            found.append(mod)
    return found

def compile_pyinstaller(ico_path):
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    hidden = detect_hidden_imports()
    cmd = [
        PY, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name", APP_NAME,
        "--add-data", f"{ROOT / 'src' / 'ui' / 'web'};src/ui/web",
        "--add-data", f"{ROOT / 'src'};src",
    ]
    if ico_path and ico_path.exists():
        cmd += ["--icon", str(ico_path)]
    for h in hidden:
        cmd += ["--hidden-import", h]
    for pkg in ("webview", "duckdb", "lancedb", "pyarrow", "arabic_reshaper", "bidi", "reportlab", "docx"):
        if pkg in hidden:
            cmd += ["--collect-all", pkg]
    cmd.append(str(ROOT / "main.py"))
    run(cmd)

def create_installer_or_package(ico_path):
    app_out = DIST_DIR / APP_NAME
    if not app_out.exists():
        raise RuntimeError("PyInstaller output folder not found!")

    # Ensure clean writable folders exist in release package
    for sub in ("data/raw_docs", "data/duckdb", "data/lancedb", "backups", "logs"):
        (app_out / sub).mkdir(parents=True, exist_ok=True)

    # Write Inno Setup Script (.iss)
    iss_path = BUILD_DIR / "eHadiPanel_Installer.iss"
    icon_line = f'SetupIconFile="{ico_path}"' if ico_path and ico_path.exists() else ""
    iss_content = f"""[Setup]
AppId={{8E4A7B12-9C3D-4F21-A812-E4AD19002026}}
AppName=eHadiPanel Enterprise
AppVersion={APP_VER}
AppPublisher=Imam Hadi (AS) Cultural & Scientific Institute
DefaultDirName={{autopf}}\\eHadiPanel
DefaultGroupName=eHadiPanel Enterprise
AllowNoIcons=yes
OutputDir={DIST_DIR}
OutputBaseFilename=eHadiPanel_Setup_v20.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
{icon_line}

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{app_out}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\eHadiPanel Enterprise"; Filename: "{{app}}\\{APP_NAME}.exe"
Name: "{{autodesktop}}\\eHadiPanel Enterprise"; Filename: "{{app}}\\{APP_NAME}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{APP_NAME}.exe"; Description: "Launch eHadiPanel Enterprise"; Flags: nowait postinstall skipifsilent
"""
    iss_path.write_text(iss_content, encoding="utf-8")

    # Search for Inno Setup Compiler (ISCC.exe)
    iscc_candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    iscc = next((p for p in iscc_candidates if p.exists()), None)

    if iscc:
        print("[INFO] Inno Setup found! Building single-file Windows Setup Installer...", flush=True)
        run([str(iscc), str(iss_path)])
        print(f"\n[SUCCESS] Windows Installer created: {DIST_DIR / 'eHadiPanel_Setup_v20.0.exe'}", flush=True)
    else:
        zip_path = DIST_DIR / "eHadiPanel_v20.0_Portable.zip"
        print("[INFO] Creating Portable ZIP release package...", flush=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in app_out.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(DIST_DIR))
        print(f"\n[SUCCESS] Standalone Executable ready: {app_out / (APP_NAME + '.exe')}", flush=True)
        print(f"[SUCCESS] Portable Archive ready: {zip_path}", flush=True)
        print(f"[TIP] Inno Setup script saved at: {iss_path}", flush=True)

if __name__ == "__main__":
    ensure_build_deps()
    patch_frozen_paths()
    ico = build_windows_icon()
    compile_pyinstaller(ico)
    create_installer_or_package(ico)
