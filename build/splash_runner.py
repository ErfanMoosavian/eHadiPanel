"""
اسپلش اسکرین رسمی و شیشه‌ای eHadiPanel Beta 0.2
مؤسسه علمی فرهنگی امام هادی علیه‌السلام
- طراحی کاملاً هم‌زبان با رابط کاربری برنامه (Obsidian Liquid Glass + Micro-Grid + Ambient Orbs)
- مونوگرام معماری و شیشه‌ای eHP در مرکز گرافیک به‌همراه کارت‌های مینی‌تحلیلی شیشه‌ای (Spline & Telemetry)
- هماهنگی خودکار با پالت رنگی انتخابی کاربر در تنظیمات (سرمه‌ای یا سبز زمردی) و لوگوی واقعی مؤسسه
- انیمیشن روان ۶۰ فریم (گوی‌های نورانی مدار، ذرات نور معلق، پالس زنده وضعیت و نوار پیشرفت راست‌به‌چپ)
- مقیاس‌پذیری واقعی DPI ویندوز (۷۶۰×۴۵۰ DIP) + کش هوشمند در TEMP (اجرای آنی زیر ۲۵ میلی‌ثانیه)
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

DESIGN_REV = "beta02_ehp_glass_v4b"
LOGICAL_W = 760
LOGICAL_H = 450

BRAND_WORDMARK = "eHadiPanel"
VERSION_BADGE = "BETA 0.2"
INST_TITLE = "مؤسسه علمی فرهنگی امام هادی علیه‌السلام"
INST_SUBTITLE = "سامانه هوشمند مدیریت، تحلیل آماری و دستیار پژوهشی"
FOOTER_META_RIGHT = "نسخه آزمایشی دوم  •  پلتفرم آفلاین و امن"
FOOTER_META_LEFT = "eHadiPanel  •  Beta 0.2"

CAPABILITY_CHIPS = [
    ("هوش تجاری", 632, 718),
    ("تحلیل اسناد", 534, 622),
    ("دستیار هوشمند", 424, 524),
]

STAGES = {
    "0": (22.0, "در حال آماده‌سازی هسته سامانه..."),
    "1": (48.0, "بارگذاری پایگاه‌داده تحلیلی و موتور اسناد..."),
    "2": (74.0, "راه‌اندازی هوش تجاری و حافظه هوشمند..."),
    "3": (92.0, "آماده‌سازی پنجره و رابط کاربری..."),
    "READY": (100.0, "سامانه آماده به کار است"),
}

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_fa_pct(val: float) -> str:
    return f"{int(round(max(0.0, min(100.0, val))))}٪".translate(FA_DIGITS)


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _get_dpi_scale(root) -> float:
    scale = 1.0
    if os.name == "nt":
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
            if dpi and dpi >= 96:
                scale = float(dpi) / 96.0
        except Exception:
            try:
                scale = float(root.winfo_fpixels("1i")) / 96.0
            except Exception:
                scale = 1.0
    else:
        try:
            scale = float(root.winfo_fpixels("1i")) / 96.0
        except Exception:
            scale = 1.0
    return max(1.0, min(2.25, scale))


def _project_roots() -> list[Path]:
    roots: list[Path] = []
    for env_k in ("EHADI_APP_DIR", "EHADI_BUNDLE_DIR"):
        v = os.environ.get(env_k)
        if v:
            roots.append(Path(v))
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
        roots.append(Path(sys.executable).resolve().parent)
    here = Path(__file__).resolve()
    roots.append(here.parent.parent)
    roots.append(Path.cwd())
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        key = str(r).lower()
        if key not in seen and r.exists():
            seen.add(key)
            out.append(r)
    return out


def _read_branding_prefs() -> tuple[str, str]:
    palette = "navy"
    logo_path = ""
    for root in _project_roots():
        bp = root / "data" / "storage" / "branding.json"
        if bp.exists():
            try:
                data = json.loads(bp.read_text(encoding="utf-8"))
                pal = str(data.get("ui_palette") or "").strip().lower()
                if pal in ("navy", "emerald"):
                    palette = pal
                lp = str(data.get("logo_path") or "").strip()
                if lp and Path(lp).exists():
                    logo_path = lp
                break
            except Exception:
                pass
    return palette, logo_path


def _find_logo_file(custom_path: str = "") -> Path | None:
    if custom_path and Path(custom_path).is_file():
        return Path(custom_path)
    candidates_rel = [
        "build/splash_logo.png",
        "build/logo.png",
        "src/ui/web/assets/ehadi_logo.png",
        "src/ui/web/assets/logo.png",
        "build/eHadiPanel.ico",
    ]
    for root in _project_roots():
        for rel in candidates_rel:
            p = root / rel
            if p.is_file():
                return p
    return None


def _pick_persian_font(tk_font_module) -> str:
    try:
        avail = {f.lower(): f for f in tk_font_module.families()}
    except Exception:
        avail = {}
    for pref in (
        "Vazirmatn",
        "Vazirmatn FD",
        "Vazir",
        "IRANSansX",
        "IRANSans",
        "Yekan Bakh",
        "Dana",
        "Shabnam",
        "Segoe UI",
        "Tahoma",
    ):
        if pref.lower() in avail:
            return avail[pref.lower()]
    return "Segoe UI"


def _pick_latin_display_font(tk_font_module) -> str:
    try:
        avail = {f.lower(): f for f in tk_font_module.families()}
    except Exception:
        avail = {}
    for pref in ("Segoe UI Variable Display", "Segoe UI", "Inter", "Bahnschrift", "Calibri"):
        if pref.lower() in avail:
            return avail[pref.lower()]
    return "Segoe UI"


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0 or os.name != "nt":
        return True
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong(0)
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return True


def _apply_win11_dwm_style(root, palette: str = "navy") -> None:
    if os.name != "nt":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        round_pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(round_pref), ctypes.sizeof(round_pref))
        # Subtle cool slate/glass border color (BGR) matching the app palette
        border_col = ctypes.c_uint(0x003D4B20 if palette == "emerald" else 0x0052371E)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_col), ctypes.sizeof(border_col))
    except Exception:
        pass


def _prepare_logo_image(logo_file: Path, target_box: int, palette: str):
    """Loads institute logo, trims padding, and illuminates dark ink logos into crisp cool platinum-white."""
    from PIL import Image
    import numpy as np

    with Image.open(logo_file) as raw:
        lg = raw.convert("RGBA")
    bbox = lg.getbbox()
    if bbox:
        lg = lg.crop(bbox)

    ratio = min(target_box / max(1, lg.width), target_box / max(1, lg.height))
    nw = max(1, int(round(lg.width * ratio)))
    nh = max(1, int(round(lg.height * ratio)))
    lg = lg.resize((nw, nh), Image.Resampling.LANCZOS)

    arr = np.array(lg, dtype=np.float32)
    mask = arr[..., 3] > 42
    if np.any(mask):
        lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
        if float(lum[mask].mean()) < 120.0:
            # Crisp cool platinum-silver tint matching app's dark glass UI
            if palette == "emerald":
                arr[..., 0], arr[..., 1], arr[..., 2] = 224.0, 248.0, 239.0
            else:
                arr[..., 0], arr[..., 1], arr[..., 2] = 228.0, 241.0, 255.0
            lg = Image.fromarray(arr.astype(np.uint8), mode="RGBA")
    return lg


def _render_artwork_uncached(W: int, H: int, palette: str, logo_file: Path | None):
    """
    App-native Executive Obsidian Glass artwork directly inspired by luxury_glass_v46.css:
    - Deep obsidian base (#040916 navy / #050a0e emerald) + ambient mesh orbs + micro-grid (.bg-grid)
    - Left Hero: Architectural layered liquid-glass monolith housing the bold `eHP` monogram,
      flanked by two ultra-clean frosted BI micro-cards (spline wave & vertical telemetry bars)
      and two precision orbital rings for the live 60 FPS animated beads.
    - Right Editorial Zone: Clean institute badge, BETA 0.2 pill, eHadiPanel wordmark,
      accent gradient bar, capability chips, and frosted glass bottom loading dock.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    scale = W / float(LOGICAL_W)

    # Exact color system from src/ui/web/luxury_glass_v46.css
    if palette == "emerald":
        bg_dark = np.array([5, 10, 14], dtype=np.float32)       # --lg-bg-dark: #050a0e
        bg_lift = np.array([10, 25, 31], dtype=np.float32)
        c_acc1 = np.array([16, 185, 129], dtype=np.float32)     # --lg-accent: #10b981
        c_acc2 = np.array([45, 212, 191], dtype=np.float32)     # --lg-accent-2: #2dd4bf
        acc1 = (16, 185, 129)
        acc2 = (45, 212, 191)
        tile_fill = (9, 20, 25, 234)
        back_tile_fill = (10, 28, 32, 105)
        card_fill = (12, 24, 30, 178)
        dock_fill = (6, 13, 17, 184)
    else:
        bg_dark = np.array([4, 9, 22], dtype=np.float32)        # --lg-bg-dark: #040916
        bg_lift = np.array([11, 22, 46], dtype=np.float32)
        c_acc1 = np.array([56, 189, 248], dtype=np.float32)     # --lg-accent: #38bdf8
        c_acc2 = np.array([129, 140, 248], dtype=np.float32)    # --lg-accent-2: #818cf8
        acc1 = (56, 189, 248)
        acc2 = (129, 140, 248)
        tile_fill = (10, 18, 36, 236)
        back_tile_fill = (14, 24, 48, 105)
        card_fill = (13, 22, 42, 178)
        dock_fill = (6, 11, 24, 186)

    # 1. Ambient Obsidian Glass Mesh & Subtle BI Spline Aurora
    gw, gh = max(240, W // 2), max(142, H // 2)
    yy, xx = np.mgrid[0:gh, 0:gw].astype(np.float32)
    nx = xx / max(1, gw - 1)
    ny = yy / max(1, gh - 1)

    diag = np.clip(nx * 0.72 + ny * 0.35, 0.0, 1.0)[..., None]
    col = bg_lift * (1.0 - diag) + bg_dark * diag

    def orb(cx_n, cy_n, rx_n, ry_n, rgb, strength):
        d2 = ((nx - cx_n) / rx_n) ** 2 + ((ny - cy_n) / ry_n) ** 2
        return rgb[None, None, :] * (np.exp(-d2 * 1.9) * strength)[..., None]

    col += orb(0.25, 0.41, 0.29, 0.42, c_acc1, 0.34)
    col += orb(0.08, 0.80, 0.30, 0.38, c_acc2, 0.28)
    col += orb(0.39, 0.14, 0.24, 0.26, c_acc2, 0.16)
    col += orb(0.92, 0.12, 0.22, 0.26, c_acc1, 0.11)

    # Smooth frosted-glass aurora curves (restrained, executive)
    wave_a = 0.62 - 0.32 * nx + 0.065 * np.sin(nx * 5.8 + 0.5)
    ribbon_a = np.exp(-((ny - wave_a) / 0.055) ** 2) * np.exp(-((nx - 0.25) / 0.34) ** 2)
    col += c_acc1[None, None, :] * (ribbon_a * 0.24)[..., None]

    wave_b = 0.28 + 0.38 * nx + 0.055 * np.cos(nx * 4.8 - 0.6)
    ribbon_b = np.exp(-((ny - wave_b) / 0.045) ** 2) * np.exp(-((nx - 0.22) / 0.32) ** 2)
    col += c_acc2[None, None, :] * (ribbon_b * 0.22)[..., None]

    line_a = np.exp(-((ny - wave_a) / 0.0065) ** 2) * np.exp(-((nx - 0.24) / 0.29) ** 2)
    col += (c_acc1 * 0.6 + np.array([255, 255, 255], dtype=np.float32) * 0.4)[None, None, :] * (line_a * 0.40)[..., None]

    # Velvet readability darkening on right text side
    r_fade = np.clip((nx - 0.45) / 0.26, 0.0, 1.0)
    r_fade = r_fade * r_fade * (3.0 - 2.0 * r_fade)
    col = col * (1.0 - 0.52 * r_fade[..., None]) + bg_dark * (0.52 * r_fade[..., None])

    vig = 1.0 - 0.26 * (((nx - 0.46) * 1.24) ** 2 + ((ny - 0.48) * 1.22) ** 2)
    col *= np.clip(vig, 0.66, 1.0)[..., None]

    base = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), mode="RGB").resize((W, H), Image.Resampling.BICUBIC).convert("RGBA")

    # Fine micro-grain eliminates 8-bit banding cleanly
    rng = np.random.default_rng(4802)
    grain = rng.normal(0.0, 1.6, (H, W, 1)).astype(np.float32)
    barr = np.array(base, dtype=np.float32)
    barr[..., :3] = np.clip(barr[..., :3] + grain, 0, 255)
    base = Image.fromarray(barr.astype(np.uint8), mode="RGBA")

    # 2. Architectural Micro-Grid (.bg-grid DNA from app) fading smoothly from hero center
    grid_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd_g = ImageDraw.Draw(grid_img)
    step_px = max(18, int(round(28 * scale)))
    for gx in range(step_px // 2, W, step_px):
        gd_g.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 16), width=1)
    for gy in range(step_px // 2, H, step_px):
        gd_g.line([(0, gy), (W, gy)], fill=(255, 255, 255, 16), width=1)
    for gx in range(step_px // 2, int(W * 0.56), step_px * 2):
        for gy in range(step_px // 2, int(H * 0.80), step_px * 2):
            gd_g.line([(gx - 3, gy), (gx + 3, gy)], fill=acc1 + (42,), width=1)
            gd_g.line([(gx, gy - 3), (gx, gy + 3)], fill=acc1 + (42,), width=1)

    g_arr = np.array(grid_img, dtype=np.float32)
    y_full, x_full = np.mgrid[0:H, 0:W].astype(np.float32)
    xn = x_full / max(1, W - 1)
    yn = y_full / max(1, H - 1)
    grid_mask = np.exp(-(((xn - 0.25) / 0.34) ** 2 + ((yn - 0.42) / 0.44) ** 2))
    g_arr[..., 3] *= np.clip(grid_mask, 0.0, 1.0)
    base = Image.alpha_composite(base, Image.fromarray(g_arr.astype(np.uint8), mode="RGBA"))

    # 3. Supersampled Executive Hero Monolith + Floating Glass BI Micro-Cards
    S = 2.0 if W <= 960 else 1.5
    SW, SH = int(round(W * S)), int(round(H * S))

    def px(dip_x: float) -> int:
        return int(round(dip_x * scale * S))

    def py(dip_y: float) -> int:
        return int(round(dip_y * scale * S))

    cx, cy = px(194), py(186)

    # Soft backlit aura behind eHP Monolith
    halo = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hr = px(94)
    hd.rounded_rectangle([cx - hr, cy - hr, cx + hr, cy + hr], radius=px(36), fill=acc1 + (46,))
    hd.ellipse([cx - px(136), cy - px(136), cx + px(136), cy + px(136)], outline=acc2 + (54,), width=max(2, px(2.5)))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=max(8, px(20))))
    base = Image.alpha_composite(base, halo.resize((W, H), Image.Resampling.BILINEAR))

    hero = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    d = ImageDraw.Draw(hero)
    lw1 = max(1, int(round(1.0 * scale * S)))
    lw2 = max(2, int(round(1.6 * scale * S)))

    # Two minimal architectural precision orbit rings (tracks for live animated light beads)
    r_orb1 = px(142)
    r_orb2 = px(106)
    d.ellipse([cx - r_orb1, cy - r_orb1, cx + r_orb1, cy + r_orb1], outline=acc1 + (36,), width=lw1)
    d.ellipse([cx - r_orb2, cy - r_orb2, cx + r_orb2, cy + r_orb2], outline=(255, 255, 255, 24), width=lw1)
    d.arc([cx - r_orb1, cy - r_orb1, cx + r_orb1, cy + r_orb1], start=208, end=318, fill=acc1 + (115,), width=lw2)
    d.arc([cx - r_orb1, cy - r_orb1, cx + r_orb1, cy + r_orb1], start=28, end=122, fill=acc2 + (95,), width=lw2)
    d.arc([cx - r_orb2, cy - r_orb2, cx + r_orb2, cy + r_orb2], start=135, end=235, fill=(255, 255, 255, 72), width=lw1)

    # Floating Smoked-Glass BI Micro-Card 1 (Top-Left: Sleek Analytics Spline Card)
    c1_x1, c1_y1, c1_x2, c1_y2 = px(44), py(58), px(152), py(118)
    d.rounded_rectangle([c1_x1, c1_y1, c1_x2, c1_y2], radius=px(12), fill=card_fill, outline=(255, 255, 255, 34), width=lw1)
    d.line([(c1_x1 + px(12), c1_y1 + 1), (c1_x2 - px(12), c1_y1 + 1)], fill=(255, 255, 255, 72), width=lw1)
    d.ellipse([c1_x2 - px(14), c1_y1 + py(10), c1_x2 - px(9), c1_y1 + py(15)], fill=acc1 + (215,))
    d.rounded_rectangle([c1_x1 + px(12), c1_y1 + py(11), c1_x1 + px(54), c1_y1 + py(15)], radius=px(2), fill=(255, 255, 255, 42))

    sp_pts = []
    for k in range(24):
        t = k / 23.0
        sx = c1_x1 + px(12) + t * (c1_x2 - c1_x1 - px(24))
        sy = c1_y2 - py(14) - (0.28 + 0.45 * t + 0.22 * math.sin(t * 5.2 - 0.4)) * py(30)
        sp_pts.append((sx, sy))
    area_pts = [(sp_pts[0][0], c1_y2 - py(8))] + sp_pts + [(sp_pts[-1][0], c1_y2 - py(8))]
    d.polygon(area_pts, fill=acc1 + (30,))
    d.line(sp_pts, fill=acc1 + (220,), width=max(2, px(1.6)), joint="curve")

    # Floating Smoked-Glass BI Micro-Card 2 (Bottom-Right of hero: Sleek Telemetry Bars)
    c2_x1, c2_y1, c2_x2, c2_y2 = px(236), py(252), px(340), py(314)
    d.rounded_rectangle([c2_x1, c2_y1, c2_x2, c2_y2], radius=px(12), fill=card_fill, outline=(255, 255, 255, 34), width=lw1)
    d.line([(c2_x1 + px(12), c2_y1 + 1), (c2_x2 - px(12), c2_y1 + 1)], fill=(255, 255, 255, 72), width=lw1)
    bar_heights = [0.42, 0.70, 0.54, 0.92, 0.68]
    bw, bgap = px(10), px(8)
    bx0, by_bot = c2_x1 + px(14), c2_y2 - py(12)
    for bi, bh_f in enumerate(bar_heights):
        bx = bx0 + bi * (bw + bgap)
        bh = int(py(36) * bh_f)
        bcol = acc1 + (225,) if bi == 3 else (acc2 + (140,) if bi % 2 == 1 else (255, 255, 255, 58))
        d.rounded_rectangle([bx, by_bot - bh, bx + bw, by_bot], radius=px(3), fill=bcol)

    # Layered Smoked-Glass Depth Backing Plate behind main eHP Monolith
    m_half = px(66)  # 132x132 DIP monolith
    off = px(9)
    d.rounded_rectangle(
        [cx - m_half - off, cy - m_half + off, cx + m_half - off, cy + m_half + off],
        radius=px(28),
        fill=back_tile_fill,
        outline=acc2 + (62,),
        width=lw1,
    )

    # MAIN HERO CENTERPIECE: Architectural Liquid-Glass `eHP` Monolith Squircle
    mx1, my1, mx2, my2 = cx - m_half, cy - m_half, cx + m_half, cy + m_half
    d.rounded_rectangle([mx1, my1, mx2, my2], radius=px(28), fill=tile_fill)

    sheen = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.rounded_rectangle([mx1 + px(3), my1 + px(3), mx2 - px(3), cy - py(2)], radius=px(24), fill=(255, 255, 255, 16))
    sd.ellipse([mx1 - px(10), my1 - px(24), cx + px(38), cy + px(14)], fill=acc1 + (26,))
    mon_mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(mon_mask).rounded_rectangle([mx1 + 2, my1 + 2, mx2 - 2, my2 - 2], radius=px(27), fill=255)
    sheen_clipped = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sheen_clipped.paste(sheen, (0, 0), mon_mask)
    hero = Image.alpha_composite(hero, sheen_clipped)
    d = ImageDraw.Draw(hero)

    # Crisp luminous rim + inner hairline glass bevel on eHP Monolith
    d.rounded_rectangle([mx1, my1, mx2, my2], radius=px(28), outline=acc1 + (178,), width=max(2, px(1.6)))
    d.rounded_rectangle([mx1 + px(5), my1 + px(5), mx2 - px(5), my2 - px(5)], radius=px(23), outline=(255, 255, 255, 26), width=lw1)
    for x in range(mx1 + px(24), mx2 - px(24)):
        t_m = 1.0 - abs((x - cx) / max(1.0, (m_half - px(24))))
        a = int(195 * (t_m ** 1.4))
        if a > 0:
            d.line([(x, my1 + 1), (x, my1 + 3)], fill=(255, 255, 255, a))

    # Crisp gradient accent bar beneath the `eHP` monogram inside the monolith
    ub_w = px(44)
    ub_y = cy + py(34)
    for x in range(cx - ub_w // 2, cx + ub_w // 2):
        t = (x - (cx - ub_w // 2)) / max(1, ub_w - 1)
        r = int(acc1[0] * (1 - t) + acc2[0] * t)
        g = int(acc1[1] * (1 - t) + acc2[1] * t)
        b = int(acc1[2] * (1 - t) + acc2[2] * t)
        d.line([(x, ub_y), (x, ub_y + max(2, py(2.6)))], fill=(r, g, b, 232))

    # 4. Right Editorial Chrome + Bottom Frosted Glass Dock
    dock_top = py(362)
    d.rectangle([0, dock_top, SW, SH], fill=dock_fill)
    for x in range(px(24), px(736)):
        t_m = 1.0 - abs((x / SW) - 0.5) * 1.95
        a = int(46 * max(0.0, t_m))
        if a > 0:
            d.line([(x, dock_top), (x, dock_top + 1)], fill=(255, 255, 255, a))

    # Top-Right Clean Glass Badge for Institute Logo (52x52 DIPs)
    sq_x1, sq_y1, sq_x2, sq_y2 = px(666), py(42), px(718), py(94)
    d.rounded_rectangle(
        [sq_x1, sq_y1, sq_x2, sq_y2],
        radius=px(13),
        fill=card_fill,
        outline=acc1 + (112,),
        width=max(2, px(1.1)),
    )
    d.line([(sq_x1 + px(10), sq_y1 + 1), (sq_x2 - px(10), sq_y1 + 1)], fill=(255, 255, 255, 78), width=lw1)

    logo_placed = False
    if logo_file is not None and logo_file.is_file():
        try:
            lg_img = _prepare_logo_image(logo_file, int(round(34 * scale * S)), palette)
            scx, scy = (sq_x1 + sq_x2) // 2, (sq_y1 + sq_y2) // 2
            hero.alpha_composite(lg_img, dest=(scx - lg_img.width // 2, scy - lg_img.height // 2))
            logo_placed = True
        except Exception:
            logo_placed = False

    if not logo_placed:
        # Clean layered-sheets icon (matches index.html .brand-logo SVG!) — zero stars
        d = ImageDraw.Draw(hero)
        scx, scy = (sq_x1 + sq_x2) // 2, (sq_y1 + sq_y2) // 2
        w_l, h_l = px(13), px(6)
        d.polygon([(scx, scy - px(12)), (scx + w_l, scy - px(6)), (scx, scy), (scx - w_l, scy - px(6))],
                  fill=acc1 + (58,), outline=acc1 + (235,), width=lw2)
        d.line([(scx - w_l, scy + px(1)), (scx, scy + h_l + px(1)), (scx + w_l, scy + px(1))],
               fill=(226, 232, 240, 210), width=lw2)
        d.line([(scx - w_l, scy + px(7)), (scx, scy + h_l + px(7)), (scx + w_l, scy + px(7))],
               fill=acc2 + (205,), width=lw2)

    # Sleek "BETA 0.2" pill matching .version-pill in luxury_glass_v46.css
    d = ImageDraw.Draw(hero)
    d.rounded_rectangle(
        [px(560), py(55), px(652), py(81)],
        radius=px(13),
        fill=acc1 + (28,),
        outline=acc1 + (108,),
        width=max(2, px(1.1)),
    )

    # Editorial gradient rule under eHadiPanel wordmark (--lg-accent -> --lg-accent-2)
    rx1, rx2, ry1, ry2 = px(652), px(718), py(184), py(187)
    for x in range(rx1, rx2):
        t = (x - rx1) / max(1, rx2 - rx1 - 1)
        r = int(acc2[0] * (1 - t) + acc1[0] * t)
        g = int(acc2[1] * (1 - t) + acc1[1] * t)
        b = int(acc2[2] * (1 - t) + acc1[2] * t)
        d.line([(x, ry1), (x, ry2)], fill=(r, g, b, 238))

    # Three clean frosted glass capability chips (matching .eh-v48-pill)
    for _, cx1, cx2 in CAPABILITY_CHIPS:
        d.rounded_rectangle(
            [px(cx1), py(286), px(cx2), py(312)],
            radius=px(13),
            fill=(255, 255, 255, 13),
            outline=(255, 255, 255, 34),
            width=max(1, px(0.9)),
        )

    # Progress bar track
    d.rounded_rectangle(
        [px(42), py(411), px(718), py(416)],
        radius=px(2.5),
        fill=(255, 255, 255, 24),
        outline=(255, 255, 255, 22),
        width=1,
    )

    # Crisp glass outer rim + luminous top specular bevel
    d.rectangle([1, 1, SW - 2, SH - 2], outline=(255, 255, 255, 38), width=2)
    for x in range(px(36), px(724)):
        t = 1.0 - abs((x / SW) - 0.30) * 1.48
        a = int(172 * max(0.0, t))
        if a > 0:
            col_e = acc1 if x < SW * 0.52 else acc2
            d.line([(x, 1), (x, 3)], fill=col_e + (a,))

    return Image.alpha_composite(base, hero.resize((W, H), Image.Resampling.LANCZOS))


def build_splash_artwork(W: int, H: int, palette: str, logo_file: Path | None):
    """Loads pre-rendered artwork from %TEMP% cache (<25ms) or renders & caches on first launch."""
    from PIL import Image

    logo_sig = "none"
    if logo_file is not None and logo_file.is_file():
        try:
            st = logo_file.stat()
            logo_sig = f"{logo_file.name}:{st.st_size}:{int(st.st_mtime)}"
        except Exception:
            logo_sig = logo_file.name

    key_raw = f"{DESIGN_REV}|{W}x{H}|{palette}|{logo_sig}"
    key_hash = hashlib.sha1(key_raw.encode("utf-8")).hexdigest()[:12]
    cache_path = Path(tempfile.gettempdir()) / f"ehadi_splash_art_{key_hash}.png"

    if cache_path.is_file():
        try:
            with Image.open(cache_path) as cached:
                if cached.size == (W, H):
                    return cached.convert("RGBA")
        except Exception:
            pass

    img = _render_artwork_uncached(W, H, palette, logo_file)
    try:
        img.save(cache_path, format="PNG", compress_level=1)
    except Exception:
        pass
    return img


def _parse_args(argv: list[str]) -> tuple[str, int]:
    ready_file = ""
    parent_pid = 0
    i = 0
    while i < len(argv):
        if argv[i] == "--ready-file" and i + 1 < len(argv):
            ready_file = argv[i + 1]
            i += 2
        elif argv[i] == "--parent-pid" and i + 1 < len(argv):
            try:
                parent_pid = int(argv[i + 1])
            except Exception:
                parent_pid = 0
            i += 2
        else:
            i += 1
    return ready_file, parent_pid


def main() -> None:
    _enable_dpi_awareness()
    ready_file, parent_pid = _parse_args(sys.argv[1:])

    try:
        import tkinter as tk
        import tkinter.font as tkfont
    except Exception:
        return

    palette, custom_logo = _read_branding_prefs()
    logo_file = _find_logo_file(custom_logo)

    # Exact colors from src/ui/web/luxury_glass_v46.css
    if palette == "emerald":
        bg_hex = "#050a0e"
        acc_hex = "#10b981"
        acc2_hex = "#2dd4bf"
        pill_hex = "#34d399"
        shimmer_hex = "#d1fae5"
    else:
        bg_hex = "#040916"
        acc_hex = "#38bdf8"
        acc2_hex = "#818cf8"
        pill_hex = "#7dd3fc"
        shimmer_hex = "#e0f2fe"

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=bg_hex)
    try:
        root.attributes("-alpha", 0.0)
    except Exception:
        pass

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    scale = _get_dpi_scale(root)
    scale = min(scale, (sw * 0.68) / LOGICAL_W, (sh * 0.68) / LOGICAL_H)
    scale = max(0.85, scale)

    W = int(round(LOGICAL_W * scale))
    H = int(round(LOGICAL_H * scale))
    x = max(0, (sw - W) // 2)
    y = max(0, (sh - H) // 2 - int(18 * scale))
    root.geometry(f"{W}x{H}+{x}+{y}")

    _apply_win11_dwm_style(root, palette)

    canvas = tk.Canvas(root, width=W, height=H, bg=bg_hex, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)

    def dx(v: float) -> float:
        return v * scale

    def dy(v: float) -> float:
        return v * scale

    try:
        from PIL import ImageTk

        art = build_splash_artwork(W, H, palette, logo_file)
        bg_photo = ImageTk.PhotoImage(art)
        canvas.create_image(0, 0, anchor="nw", image=bg_photo)
        canvas._bg_ref = bg_photo
    except Exception:
        canvas.create_rectangle(1, 1, W - 1, H - 1, outline=acc_hex, width=1)

    ui_font = _pick_persian_font(tkfont)
    latin_font = _pick_latin_display_font(tkfont)

    # Exact pixel-locked font sizes (100% immune to DPI drift)
    f_badge = (latin_font, -max(10, int(round(11 * scale))), "bold")
    f_brand = (latin_font, -max(24, int(round(34 * scale))), "bold")
    f_title = (ui_font, -max(14, int(round(17.5 * scale))), "bold")
    f_sub = (ui_font, -max(10, int(round(12.2 * scale))))
    f_chip = (ui_font, -max(9, int(round(10.8 * scale))), "bold")
    f_status = (ui_font, -max(10, int(round(12.2 * scale))))
    f_pct = (ui_font, -max(11, int(round(13.0 * scale))), "bold")
    f_meta = (ui_font, -max(8, int(round(9.8 * scale))))
    f_meta_en = (latin_font, -max(8, int(round(9.8 * scale))), "bold")

    # =========================================================================
    # CENTERPIECE ARCHITECTURAL `eHP` MONOGRAM (Exact Measured Kerning)
    # =========================================================================
    ehp_px = max(32, int(round(46 * scale)))
    ehp_font_obj = tkfont.Font(root=root, family=latin_font, size=-ehp_px, weight="bold")
    w_e = ehp_font_obj.measure("e")
    w_hp = ehp_font_obj.measure("HP")
    w_tot = w_e + w_hp
    mon_cx, mon_cy = dx(194), dy(179)
    start_x = mon_cx - w_tot / 2.0

    # Crisp depth shadow behind `eHP` for sculpted glass relief
    sh_off = max(1.0, 1.8 * scale)
    canvas.create_text(start_x + sh_off, mon_cy + sh_off, text="e", fill="#020612", font=ehp_font_obj, anchor="w")
    canvas.create_text(start_x + w_e + sh_off, mon_cy + sh_off, text="HP", fill="#020612", font=ehp_font_obj, anchor="w")
    # Foreground dual-tone architectural monogram: luminous accent `e` + crisp platinum `HP`
    canvas.create_text(start_x, mon_cy, text="e", fill=acc_hex, font=ehp_font_obj, anchor="w")
    canvas.create_text(start_x + w_e, mon_cy, text="HP", fill="#f8fafc", font=ehp_font_obj, anchor="w")

    # Right Editorial Typography
    canvas.create_text(dx(606), dy(68), text=VERSION_BADGE, fill=pill_hex, font=f_badge, anchor="center")
    canvas.create_text(dx(718), dy(150), text=BRAND_WORDMARK, fill="#f8fafc", font=f_brand, anchor="e")
    canvas.create_text(dx(718), dy(216), text=INST_TITLE, fill="#f8fafc", font=f_title, anchor="e")
    canvas.create_text(dx(718), dy(248), text=INST_SUBTITLE, fill="#94a3b8", font=f_sub, anchor="e")

    for label, cx1, cx2 in CAPABILITY_CHIPS:
        canvas.create_text(dx((cx1 + cx2) / 2.0), dy(299), text=label, fill="#cbd5e1", font=f_chip, anchor="center")

    # =========================================================================
    # SMOOTH 60 FPS EXECUTIVE MOTION (Orbital Beads, Spline Tracer, Motes)
    # =========================================================================
    orb_cx, orb_cy = dx(194), dy(186)
    orb1_r, orb2_r = dx(142), dx(106)
    orb1_glow = canvas.create_oval(0, 0, 0, 0, fill=acc_hex, outline="")
    orb1_core = canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")
    orb2_glow = canvas.create_oval(0, 0, 0, 0, fill=acc2_hex, outline="")
    orb2_core = canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")

    # Live glowing tracer dot gliding smoothly along the top-left BI mini-spline curve
    sp_dot_halo = canvas.create_oval(0, 0, 0, 0, fill="", outline=acc_hex, width=max(1, int(scale)))
    sp_dot_core = canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline=acc_hex, width=max(1, int(scale)))

    # Subtle upward-drifting glass micro-particles in left hero space
    mote_specs = [
        (0.07, 0.72, 1.9, 0.00050, acc_hex),
        (0.14, 0.30, 1.6, 0.00038, acc2_hex),
        (0.36, 0.65, 2.0, 0.00045, acc_hex),
        (0.41, 0.25, 1.5, 0.00054, "#cbd5e1"),
        (0.11, 0.48, 1.7, 0.00036, acc2_hex),
        (0.29, 0.78, 1.8, 0.00046, "#cbd5e1"),
    ]
    mote_items = []
    for mx, my, mr, mspd, mcol in mote_specs:
        oid = canvas.create_oval(0, 0, 0, 0, fill=mcol, outline="")
        mote_items.append([oid, mx, my, mr * scale, mspd])

    # Bottom Loading Dock Dynamic Elements
    dot_r = max(3.0, 3.6 * scale)
    dot_cx, dot_cy = dx(714), dy(388)
    status_dot_halo = canvas.create_oval(
        dot_cx - dot_r * 1.9, dot_cy - dot_r * 1.9, dot_cx + dot_r * 1.9, dot_cy + dot_r * 1.9,
        fill="", outline=acc_hex, width=max(1, int(scale)),
    )
    canvas.create_oval(
        dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r,
        fill=acc_hex, outline="",
    )

    status_txt = canvas.create_text(dx(700), dy(388), text=STAGES["0"][1], fill="#e2e8f0", font=f_status, anchor="e")
    pct_txt = canvas.create_text(dx(42), dy(388), text=_to_fa_pct(6), fill=pill_hex, font=f_pct, anchor="w")

    bar_x1, bar_x2 = dx(42), dx(718)
    bar_y1, bar_y2 = dy(411), dy(416)
    bar_span = bar_x2 - bar_x1

    fill_bar = canvas.create_rectangle(bar_x2 - dx(10), bar_y1, bar_x2, bar_y2, fill=acc_hex, outline="")
    lead_tip = canvas.create_rectangle(bar_x2 - dx(14), bar_y1, bar_x2 - dx(6), bar_y2, fill=acc2_hex, outline="")
    shimmer_bar = canvas.create_rectangle(bar_x2, bar_y1, bar_x2, bar_y2, fill=shimmer_hex, outline="")

    canvas.create_text(dx(718), dy(434), text=FOOTER_META_RIGHT, fill="#64748b", font=f_meta, anchor="e")
    canvas.create_text(dx(42), dy(434), text=FOOTER_META_LEFT, fill="#64748b", font=f_meta_en, anchor="w")

    state = {
        "t0": time.monotonic(),
        "alpha": 0.0,
        "pct": 6.0,
        "target_pct": 24.0,
        "status": STAGES["0"][1],
        "ready": False,
        "ready_at": 0.0,
        "closing": False,
        "shimmer": 0.0,
        "theta": 0.0,
        "spline_t": 0.15,
        "last_pid_chk": 0.0,
    }

    if not parent_pid and not ready_file:
        root.bind("<Escape>", lambda _e: state.__setitem__("closing", True))
        canvas.bind("<Button-1>", lambda _e: state.__setitem__("closing", True))

    def _poll_stage() -> None:
        now = time.monotonic()
        elapsed = now - state["t0"]

        if parent_pid and (now - state["last_pid_chk"] > 0.45):
            state["last_pid_chk"] = now
            if not _is_pid_alive(parent_pid):
                state["closing"] = True
                return

        if ready_file:
            rf = Path(ready_file)
            if rf.exists():
                try:
                    raw = rf.read_text(encoding="utf-8").strip().upper()
                    if raw in STAGES:
                        tp, lbl = STAGES[raw]
                        if tp > state["target_pct"]:
                            state["target_pct"] = tp
                        state["status"] = lbl
                        if raw == "READY" and not state["ready"]:
                            state["ready"] = True
                            state["ready_at"] = now
                except Exception:
                    pass
        else:
            if elapsed > 0.85 and state["target_pct"] < 48:
                state["target_pct"], state["status"] = STAGES["1"]
            if elapsed > 1.85 and state["target_pct"] < 74:
                state["target_pct"], state["status"] = STAGES["2"]
            if elapsed > 2.85 and state["target_pct"] < 92:
                state["target_pct"], state["status"] = STAGES["3"]
            if elapsed > 3.85 and not state["ready"]:
                state["target_pct"], state["status"] = STAGES["READY"]
                state["ready"] = True
                state["ready_at"] = now

        if elapsed > 16.0 and not state["ready"]:
            state["ready"] = True
            state["ready_at"] = now
            state["target_pct"] = 100.0

    def _tick() -> None:
        _poll_stage()
        now = time.monotonic()

        if state["closing"]:
            state["alpha"] = max(0.0, state["alpha"] - 0.11)
            try:
                root.attributes("-alpha", state["alpha"])
            except Exception:
                pass
            if state["alpha"] <= 0.02:
                if ready_file:
                    try:
                        Path(ready_file).unlink(missing_ok=True)
                    except Exception:
                        pass
                root.destroy()
                return
        elif state["alpha"] < 1.0:
            state["alpha"] = min(1.0, state["alpha"] + 0.09)
            try:
                root.attributes("-alpha", state["alpha"])
            except Exception:
                pass

        # 1. Orbital precision beads gliding smoothly around the `eHP` monolith
        state["theta"] += 0.020
        a1 = state["theta"] - 0.9
        a2 = -state["theta"] * 1.40 + 1.1
        ox1, oy1 = orb_cx + orb1_r * math.cos(a1), orb_cy + orb1_r * math.sin(a1)
        ox2, oy2 = orb_cx + orb2_r * math.cos(a2), orb_cy + orb2_r * math.sin(a2)
        g1, c1 = 5.0 * scale, 2.2 * scale
        g2, c2 = 4.2 * scale, 1.9 * scale
        canvas.coords(orb1_glow, ox1 - g1, oy1 - g1, ox1 + g1, oy1 + g1)
        canvas.coords(orb1_core, ox1 - c1, oy1 - c1, ox1 + c1, oy1 + c1)
        canvas.coords(orb2_glow, ox2 - g2, oy2 - g2, ox2 + g2, oy2 + g2)
        canvas.coords(orb2_core, ox2 - c2, oy2 - c2, ox2 + c2, oy2 + c2)

        # 2. Live telemetry tracer gliding along top-left BI spline micro-card
        state["spline_t"] = (state["spline_t"] + 0.0075) % 1.0
        st = state["spline_t"]
        spx = dx(56 + st * 84.0)
        spy = dy(104 - (0.28 + 0.45 * st + 0.22 * math.sin(st * 5.2 - 0.4)) * 30.0)
        sr_c, sr_h = 2.6 * scale, (4.8 + 1.4 * math.sin(state["theta"] * 4.0)) * scale
        canvas.coords(sp_dot_halo, spx - sr_h, spy - sr_h, spx + sr_h, spy + sr_h)
        canvas.coords(sp_dot_core, spx - sr_c, spy - sr_c, spx + sr_c, spy + sr_c)

        # 3. Drifting ambient glass motes
        for m in mote_items:
            m[2] -= m[4]
            if m[2] < 0.06:
                m[2] = 0.77
            mx_px = m[1] * W + math.sin(state["theta"] * 1.2 + m[1] * 20.0) * (2.6 * scale)
            my_px = m[2] * H
            rr = m[3]
            canvas.coords(m[0], mx_px - rr, my_px - rr, mx_px + rr, my_px + rr)

        # 4. Breathing pulse on live status dot
        pulse = 1.45 + 0.55 * (0.5 + 0.5 * math.sin(state["theta"] * 3.0))
        hr = dot_r * pulse
        canvas.coords(status_dot_halo, dot_cx - hr, dot_cy - hr, dot_cx + hr, dot_cy + hr)

        # 5. Smooth RTL progress bar + leading accent-2 tip + gliding shimmer
        speed = 0.28 if state["ready"] else 0.08
        state["pct"] += (state["target_pct"] - state["pct"]) * speed
        if not state["ready"] and state["pct"] < min(94.0, state["target_pct"] + 4.0):
            state["pct"] += 0.12
        if state["ready"] and state["pct"] > 99.3:
            state["pct"] = 100.0

        cur_w = max(dx(12), (state["pct"] / 100.0) * bar_span)
        fx1 = bar_x2 - cur_w
        canvas.coords(fill_bar, fx1, bar_y1, bar_x2, bar_y2)
        tip_w = min(dx(36), cur_w * 0.35)
        canvas.coords(lead_tip, fx1, bar_y1, fx1 + tip_w, bar_y2)

        state["shimmer"] = (state["shimmer"] + 0.032) % 1.38
        sh_w = min(dx(56), cur_w * 0.42)
        sx2 = bar_x2 - (state["shimmer"] * cur_w)
        sx1 = max(fx1, sx2 - sh_w)
        sx2 = min(bar_x2, max(sx1, sx2))
        if sx2 - sx1 > 2:
            canvas.coords(shimmer_bar, sx1, bar_y1, sx2, bar_y2)
        else:
            canvas.coords(shimmer_bar, bar_x2, bar_y1, bar_x2, bar_y2)

        canvas.itemconfigure(status_txt, text=state["status"])
        canvas.itemconfigure(pct_txt, text=_to_fa_pct(state["pct"]))

        if state["ready"] and state["pct"] >= 99.9 and (now - state["ready_at"] >= 0.25):
            state["closing"] = True

        root.after(16, _tick)

    root.after(10, _tick)
    try:
        root.mainloop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
