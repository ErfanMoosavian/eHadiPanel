# ==============================================================================
# اسکریپت نصب خودکار سامانه مدیریت و تحلیل هوشمند eHadiPanel (نسخه v0.4.0-beta)
# مؤسسه علمی فرهنگی امام هادی (علیه‌السلام)
# ==============================================================================
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   نصب و راه‌اندازی خودکار سامانه مدیریت eHadiPanel v0.4.0-beta   " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

# ۱. پیدا کردن مفسر واقعی Python (نادیده گرفتن شورتکات جعلی WindowsApps)
function Find-RealPython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $p = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim()
            if ($p -and (Test-Path $p) -and ($p -notlike "*WindowsApps*")) { return $p }
        } catch {}
    }
    foreach ($cmdName in @("python", "python3")) {
        $cmds = Get-Command $cmdName -All -ErrorAction SilentlyContinue
        foreach ($c in $cmds) {
            if ($c.Source -and ($c.Source -notlike "*WindowsApps*") -and (Test-Path $c.Source)) {
                return $c.Source
            }
        }
    }
    $localPy = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python3*" -Filter "python.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($localPy) { return $localPy.FullName }
    return $null
}

$PyExe = Find-RealPython

if (-not $PyExe) {
    Write-Host "[1/5] پایتون روی سیستم یافت نشد؛ در حال نصب خودکار Python 3.12 از طریق winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        Start-Sleep -Seconds 2
        $PyExe = Find-RealPython
    }
}

if (-not $PyExe) {
    Write-Host "[خطا] پایتون به‌صورت خودکار نصب نشد." -ForegroundColor Red
    Write-Host "لطفاً ابتدا Python 3.11 یا 3.12 را از python.org نصب کنید (تیک Add python.exe to PATH را بزنید) و دوباره این دستور را اجرا کنید." -ForegroundColor Yellow
    exit 1
}

$PyVer = & $PyExe --version
Write-Host "[1/5] مفسر پایتون شناسایی شد: $PyVer ($PyExe)" -ForegroundColor Green

# ۲. ساخت محیط مجازی (venv)
$VenvPy = Join-Path $RootDir "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "[2/5] در حال ساخت محیط ایزوله برنامه (venv)..." -ForegroundColor Cyan
    & $PyExe -m venv venv
} else {
    Write-Host "[2/5] محیط مجازی (venv) از قبل آماده است." -ForegroundColor Green
}

# ۳. به‌روزرسانی pip و نصب پیش‌نیازها (با باینری آماده و بدون نیاز به Build Tools)
Write-Host "[3/5] در حال نصب کتابخانه‌های تحلیلی، رابط گرافیکی و گزارش‌ساز (ممکن است ۲ تا ۴ دقیقه طول بکشد)..." -ForegroundColor Cyan
& $VenvPy -m pip install --upgrade pip setuptools wheel --quiet
& $VenvPy -m pip install --prefer-binary -r requirements.txt

# ۴. ایجاد پوشه‌های کاری و فایل تنظیمات .env
Write-Host "[4/5] در حال آماده‌سازی پوشه‌های دیتابیس و تنظیمات اولیه..." -ForegroundColor Cyan
foreach ($sub in @("data", "data\raw_docs", "data\duckdb", "data\lancedb", "data\storage", "backups", "logs")) {
    $target = Join-Path $RootDir $sub
    if (-not (Test-Path $target)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }
}
if (-not (Test-Path (Join-Path $RootDir ".env")) -and (Test-Path (Join-Path $RootDir ".env.example"))) {
    Copy-Item (Join-Path $RootDir ".env.example") (Join-Path $RootDir ".env")
}

# ۵. تست سلامت ماژول‌ها و ساخت میانبر دسکتاپ
Write-Host "[5/5] بررسی سلامت نهایی ماژول‌ها..." -ForegroundColor Cyan
& $VenvPy -c "import webview, duckdb, lancedb, pandas, openpyxl, docx, pptx, fitz, PIL; print('ALL_MODULES_OK')"

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [Environment]::GetFolderPath("Desktop")
    $Shortcut = $WshShell.CreateShortcut((Join-Path $DesktopPath "eHadiPanel.lnk"))
    $Shortcut.TargetPath = Join-Path $RootDir "run.bat"
    $Shortcut.WorkingDirectory = $RootDir
    $IcoFile = Join-Path $RootDir "build\eHadiPanel.ico"
    if (Test-Path $IcoFile) { $Shortcut.IconLocation = $IcoFile }
    $Shortcut.Save()
    Write-Host "[OK] میانبر اجرایی eHadiPanel روی دسکتاپ ساخته شد." -ForegroundColor Green
} catch {}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "   نصب با موفقیت کامل انجام شد!                                   " -ForegroundColor Green
Write-Host "   برای اجرا روی فایل run.bat یا آیکون دسکتاپ کلیک کنید.           " -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""
