# راهنمای نصب و راه‌اندازی سریع سامانه eHadiPanel (ویندوز ۱۰ و ۱۱)

این راهنما طوری نوشته شده که هر کاربری بدون نیاز به دانش برنامه‌نویسی، تنها با کپی کردن دستورات داخل **PowerShell** بتواند برنامه را در چند دقیقه نصب و اجرا کند.

---

## روش اول: نصب کاملاً خودکار با کپی کردن یک بلوک دستور در PowerShell (پیشنهادی)

1. در ویندوز کلید **Win + X** را بزنید و گزینه **Terminal** یا **Windows PowerShell** را انتخاب کنید.
2. کل بلوک زیر را یکجا کپی کنید، داخل پنجره PowerShell راست‌کلیک (Paste) کنید و **Enter** بزنید:

```powershell
# ۱. دانلود و ورود به پوشه پروژه (در صورت دانلود دستی ZIP، وارد پوشه پروژه شوید)
git clone https://github.com/Erfanmoosavian/eHadiPanel.git
cd eHadiPanel

# ۲. اجرای اسکریپت نصب خودکار (نصب پایتون در صورت نبود، ساخت venv، نصب کتابخانه‌ها و ساخت میانبر دسکتاپ)
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

# ۳. اجرای برنامه
.\run.bat
```

> **نکته:** اگر پروژه را به‌صورت فایل فشرده (`.zip`) از گیت‌هاب دانلود کرده‌اید، کافی است آن را Extract کنید، داخل پوشه برنامه راست‌کلیک کرده و **Open in Terminal** را بزنید و فقط دو خط زیر را اجرا کنید:
> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
> .\run.bat
> ```

---

## روش دوم: اجرای مستقیم دستورات گام‌به‌گام (بدون نیاز به فایل اسکریپت)

اگر به هر دلیلی نمی‌خواهید فایل `install.ps1` را اجرا کنید، این دستورات را به ترتیب در PowerShell اجرا کنید:

```powershell
# گام ۱: نصب Python 3.12 (اگر پایتون روی سیستم نصب نیست)
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements

# گام ۲: ساخت محیط مجازی ایزوله
python -m venv venv

# گام ۳: به‌روزرسانی ابزار نصب و نصب تمام کتابخانه‌ها از روی باینری آماده
.\venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\venv\Scripts\python.exe -m pip install --prefer-binary -r requirements.txt

# گام ۴: ساخت فایل تنظیمات اولیه
if (!(Test-Path .env)) { Copy-Item .env.example .env }

# گام ۵: اجرای برنامه
.\venv\Scripts\python.exe .\main.py
```

---

## راه‌اندازی دستیار هوشمند آنلاین (اختیاری)

تمامی بخش‌های آفلاین برنامه (**داشبورد BI، مرکز آمار، بانک دانش‌پژوهان و پرونده ۳۶۰ درجه، ورودی پرس‌لاین، لیست خاکستری و سیاه، تولید گزارش‌های Word/Excel/PDF و تبدیل صوت آفلاین**) بدون اینترنت و بدون کلید API کار می‌کنند.

برای فعال‌سازی بخش **گفت‌وگو و تحلیل هوشمند با Gemini**:
1. یک کلید رایگان از [Google AI Studio](https://aistudio.google.com/apikey) دریافت کنید.
2. داخل برنامه وارد بخش **تنظیمات** شوید، کلید API را وارد و ذخیره کنید (یا مستقیماً در فایل `.env` مقابل `GEMINI_API_KEY` قرار دهید).

---

## رفع مشکلات احتمالی هنگام نصب

| خطای احتمالی | علت | راه‌حل فوری در PowerShell |
| :--- | :--- | :--- |
| `Python was not found` یا باز شدن Microsoft Store | پایتون نصب نیست یا شورتکات جعلی ویندوز فعال است | اجرای `winget install -e --id Python.Python.3.12` و بستن و باز کردن مجدد PowerShell |
| `running scripts is disabled on this system` | محدودیت امنیتی پیش‌فرض PowerShell ویندوز | اجرای دستور با `-ExecutionPolicy Bypass` (مطابق روش اول) یا اجرای `.\venv\Scripts\python.exe .\main.py` |
| خطای باز نشدن پنجره گرافیکی در ویندوزهای قدیمی | نبود موتور نمایشگر مدرن ویندوز (Edge WebView2) | اجرای `winget install -e --id Microsoft.EdgeWebView2Runtime` |
| خطای دسترسی در `pyodbc` برای فایل‌های Access (`.accdb`) | نبود درایور Microsoft Access Database Engine | نصب بسته رایگان *Microsoft Access Database Engine 2016 Redistributable (64-bit)* |
