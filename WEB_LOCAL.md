# نسخه وب (محلی) eHadiPanel

اجرای برنامه در مرورگر روی همین کامپیوتر؛ با ورود و نقش‌های دسترسی. نسخه‌ی دسکتاپ (`run.bat`) دست‌نخورده می‌ماند.

## راه‌اندازی
```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\venv\Scripts\python.exe manage_users.py roles
.\venv\Scripts\python.exe manage_users.py add USERNAME "نام نمایشی" admin   # رمز پرسیده می‌شود
.\run_web.bat            # http://127.0.0.1:8000
```
- هیچ رمز پیش‌فرضی وجود ندارد. اولین مدیر را با دستور بالا بسازید.
- `run_web.bat --lan` برای دسترسی از شبکه‌ی داخلی (بدون HTTPS؛ فقط شبکه‌ی مطمئن).
- مدیریت کاربران: `manage_users.py list | passwd | role | disable | enable`.

## نقش‌ها
`admin` (مدیرعامل و مدیر، دسترسی تام و برابر)، `office_head`، `alumni_affairs`، `course_designer`، `executive`، `speech_flag`.
مجوزها در `src/web/permissions.py` هستند؛ هر متد جدید `AppAPI` باید آنجا طبقه‌بندی شود (تست این را اجبار می‌کند).

## هنوز انجام نشده
- خروجی اکسل/ورد/PDF و آپلود فایل از طریق مرورگر (فعلاً پیام «در نسخه وب فعال نیست»).
- فیلتر بخش مالی داخل داشبورد برای نقش‌های بدون دسترسی مالی؛ تا آن زمان دستیار هوشمند فقط برای `admin` باز است.
- تاریخچه‌ی گفتگوی هوشمند بین کاربران مشترک است.
- دسترسی «فقط دوره‌های خودش» (خطابه/پرچمداران) و تغییر رمز از داخل رابط.

## تست
`python -m pytest tests -q`
