# سامانه مدیریت و تحلیل هوشمند eHadiPanel (`v0.4.0-beta`)

نرم‌افزار دسکتاپی ویندوز برای یکپارچه‌سازی و تحلیل هوشمند فایل‌های اکسل، ورد، پاورپوینت، PDF و اکسس مؤسسه علمی فرهنگی امام هادی (علیه‌السلام)؛ شامل داشبورد BI، مرکز آمار، بانک یکتاسازی‌شده دانش‌پژوهان و پرونده ۳۶۰ درجه، سیستم لیست خاکستری/سیاه، تطبیق پرس‌لاین و گزارش‌ساز رسمی (Excel / Word / PDF).

---

## نصب سریع در ویندوز ۱۰ و ۱۱ (کپی و اجرا در PowerShell)

کلید **Win + X** را بزنید، **Terminal / PowerShell** را باز کنید و کد زیر را یکجا اجرا کنید:

```powershell
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements }
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements }
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

git clone https://github.com/Erfanmoosavian/eHadiPanel.git
cd eHadiPanel
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
.\run.bat
```

## نصب دستی (در صورت نیاز)

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\venv\Scripts\python.exe -m pip install --prefer-binary -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\venv\Scripts\python.exe .\main.py
```

## اجرا در دفعات بعدی
روی آیکون **eHadiPanel** روی دسکتاپ یا فایل **`run.bat`** دوبار کلیک کنید.

> تمامی بخش‌های آماری و گزارش‌ساز **آفلاین** کار می‌کنند. برای دستیار هوشمند آنلاین، کلید `GEMINI_API_KEY` را در تنظیمات برنامه یا فایل `.env` وارد کنید.