"""Run the local web edition:  python run_web.py   ->  http://127.0.0.1:8000

  --lan        listen on the local network (0.0.0.0). No HTTPS: use only on a trusted LAN.
  --port N     port (default 8000)
  --no-browser don't open the browser
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

os.environ["EHADI_WEB"] = "1"  # tells main.py not to start the desktop splash/window hooks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    host = "0.0.0.0" if args.lan else args.host

    from src.core.config import Config
    from src.core.safety import log_audit
    from src.web.auth import AuthStore
    from src.core.taxonomy import get_taxonomy
    from src.web.server import create_app, disable_desktop_side_effects
    from src.web.services import TaxonomyService

    auth = AuthStore(Config.DATA_DIR / "web_auth.sqlite3")
    if not auth.list_users():
        print("هنوز هیچ کاربری ساخته نشده است. اول یک مدیر بسازید:\n"
              '  python manage_users.py add USERNAME "نام نمایشی" admin')
        return 1

    import uvicorn
    import main as desktop  # AppAPI lives here; EHADI_WEB keeps its desktop side effects off

    disable_desktop_side_effects()  # exports are downloaded by the browser, not opened on the server
    api = desktop.AppAPI()
    app = create_app(api, auth, services=[TaxonomyService(api, get_taxonomy())], secure_cookie=os.environ.get("EHADI_WEB_SECURE") == "1", audit=log_audit,
                     work_dir=Config.DATA_DIR / "web_tmp")
    if args.lan:
        print("هشدار: دسترسی شبکه‌ای بدون HTTPS است؛ فقط در شبکه‌ی داخلی مطمئن استفاده کنید.")
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '127.0.0.1') else host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"eHadiPanel (web, local) روی {url}")
    uvicorn.run(app, host=host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
