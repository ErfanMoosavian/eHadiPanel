# راهنمای کامل اجرای نسخه وب (لوکال) با PowerShell

## پیش‌نیاز
ویندوز ۱۰/۱۱ و Python 3.10+ (اگر نبود، اسکریپت با winget نصب می‌کند).

## ۱) باز کردن پوشه پروژه
```powershell
cd C:\path\to\ehadipanel
git checkout web-local      # یا شاخه‌ای که این فایل‌ها در آن است
```
اگر ExecutionPolicy جلوی اسکریپت را گرفت (فقط برای همین پنجره):
```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

## ۲) نصب (یک‌بار)
```powershell
.\setup_web.ps1
```
ساخت venv، نصب بسته‌ها، ساخت پوشه‌های data/backups/logs و کپی `.env`.

## ۳) کلید Gemini (اختیاری)
فایل `.env` را باز کنید و کلید را بگذارید (یا از تنظیمات داخل برنامه).

## ۴) ساخت اولین مدیر
```powershell
.\setup_web.ps1 -AddAdmin
```
رمز هر طولی (موقت). کاربران دیگر:
```powershell
.\venv\Scripts\python manage_users.py roles
.\venv\Scripts\python manage_users.py add kamandi "علی کمندی" alumni_affairs
.\venv\Scripts\python manage_users.py list
.\venv\Scripts\python manage_users.py passwd kamandi
.\venv\Scripts\python manage_users.py disable kamandi
```

## ۵) اجرا
```powershell
.\setup_web.ps1 -Run              # http://127.0.0.1:8765
.\setup_web.ps1 -Run -Port 9000
.\setup_web.ps1 -Run -Lan         # دسترسی از شبکه داخلی (بدون HTTPS)
```
برای دسترسی از سیستم‌های دیگر در LAN، فایروال ویندوز پورت را باید اجازه دهد:
```powershell
New-NetFirewallRule -DisplayName ehadi -Direction Inbound -LocalPort 8765 -Protocol TCP -Action Allow
```

## ۶) تست
```powershell
.\setup_web.ps1 -Test
```

## ۷) بکاپ
```powershell
Compress-Archive -Path data -DestinationPath ("backups\data-{0:yyyyMMdd-HHmm}.zip" -f (Get-Date))
```
قبل از بکاپ سرور را متوقف کنید.

## فایل‌های requirements
- `requirements.txt` — هسته + وب (کافی برای نسخه وب)
- `requirements-desktop.txt` — فقط برای پنجره دسکتاپ قدیمی (pywebview)
- `requirements-voice.txt` — دستیار صوتی (فقط دسکتاپ)
- `requirements-dev.txt` — تست

حذف‌شده از قبلی: pywin32، XlsxWriter، psutil (در کد استفاده نشده‌اند)، و pyarrow/numpy/pydantic/requests که خودکار نصب می‌شوند. اضافه‌شده: starlette، uvicorn؛ edge-tts به فایل voice رفت (قبلاً در لیست نبود).

## مشکلات رایج
- `Python not found`: پنجره PowerShell جدید باز کنید.
- پورت اشغال: `-Port 9000`.
- وارد نمی‌شود پس از ۵ رمز غلط: ۵ دقیقه صبر کنید.

## خلاصه جلسات
بعد از ورود، لینک «خلاصه جلسات» پایین صفحه است (یا `/summaries`). طراح آموزشی و مدیر می‌توانند ثبت و ویرایش کنند؛ بقیه فقط می‌بینند. داده‌ها در `data/session_summaries.sqlite3` ذخیره می‌شوند و در بکاپ پوشهٔ `data` می‌آیند.
