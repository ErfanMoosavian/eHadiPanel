import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

from src.core.config import BASE_DIR, Config

BRANDING_FILE = Config.STORAGE_DIR / "branding.json"
SUITE_FILE = Config.STORAGE_DIR / "ehadi_suite.json"
FONTS_DIR = Config.STORAGE_DIR / "fonts"
DEFAULT_LOGO_DEST = BASE_DIR / "src" / "ui" / "web" / "assets" / "logo.png"

HONORIFIC_AS = "\u0611"  # سیمبل ریز علیه‌السلام ؑ

THEMES = {
    "emerald_beige": {
        "name": "سبز زمردی و بژ سازمانی",
        "primary": "0B8443",
        "dark": "07592D",
        "accent": "CEC8A6",
        "accent_soft": "F2EFE1",
        "light": "F4F8F5",
        "pill_bg": "CFCAA9",
    },
    "steel_beige": {
        "name": "آبی فولادی و بژ سازمانی",
        "primary": "1B5E73",
        "dark": "103846",
        "accent": "CEC8A6",
        "accent_soft": "F2EFE1",
        "light": "EFF5F7",
        "pill_bg": "D8D2B5",
    },
}

DEFAULT_BRANDING: dict[str, Any] = {
    "org_name": f"گروه علمی فرهنگی امام هادی{HONORIFIC_AS}",
    "unit_name": "سامانه هوشمند مدیریت، پژوهش و آموزش",
    "default_intro_text": "با سلام و احترام؛ گزارش تحلیلی و مستند زیر بر اساس داده‌های ثبت‌شده در سامانه هوشمند مؤسسه به استحضار می‌رسد.",
    "footer_text": f"مؤسسه علمی فرهنگی امام هادی{HONORIFIC_AS}",
    "contact_phone": "۰۲۵-۳۷۷۲۵۲۲۵-۷",
    "contact_handle": "@emamhadi_qom",
    "contact_text": "۰۲۵-۳۷۷۲۵۲۲۵-۷",
    "signature_title": "با تشکر و احترام — مدیریت مؤسسه",
    "excel_default_title": f"گزارش رسمی مؤسسه امام هادی{HONORIFIC_AS}",
    "theme": "emerald_beige",
    "show_bismillah": False,
    "show_signature": True,
    "logo_path": str(DEFAULT_LOGO_DEST) if DEFAULT_LOGO_DEST.exists() else "",
    "pdf_font": "Vazirmatn",
    "word_font": "Tahoma",
    "excel_font": "Tahoma",
    "custom_fonts": [],
    "voice_engine": "gemini",
    "voice_tts": True,
    "whisper_model": "small",
    "ui_palette": "navy",
}

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_fa_digits(text: Any) -> str:
    return str(text or "").translate(PERSIAN_DIGITS)


def normalize_honorifics(text: Any) -> str:
    s = str(text or "")
    s = re.sub(r"\s*\(\s*[عص]\s*\)", HONORIFIC_AS, s)
    s = re.sub(r"\s*[«»\(]?\s*علیه[‌\s]*السلام\s*[»\)]?", HONORIFIC_AS, s)
    s = re.sub(r"\s*[—–\-|]?\s*محرمانه\s*/?\s*ویژه\s*استفاده\s*مدیریتی", "", s)
    s = re.sub(r"\s*[—–\-|]?\s*تولیدشده\s*توسط\s*سامانه\s*هوشمند\s*مدیریت\s*", "", s)
    return s.strip()


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def today_jalali_str() -> str:
    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    return to_fa_digits(f"{jy}/{jm:02d}/{jd:02d}")


def _next_letter_number() -> str:
    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    seq = 1
    try:
        if SUITE_FILE.exists():
            data = json.loads(SUITE_FILE.read_text(encoding="utf-8"))
            seq = int(data.get("letter_seq", 0)) + 1
    except Exception:
        seq = int(now.strftime("%H%M"))
    return to_fa_digits(f"{jy % 100:02d}/{jm:02d}{jd:02d}/{seq:03d}")


def register_exported_letter(title: str, fmt: str, file_path: str, letter_no: str, recipient: str = "") -> None:
    try:
        Config.ensure_directories()
        data: dict[str, Any] = {}
        if SUITE_FILE.exists():
            try:
                data = json.loads(SUITE_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        letters = list(data.get("letters") or [])
        seq = int(data.get("letter_seq", len(letters))) + 1
        data["letter_seq"] = seq
        letters.insert(
            0,
            {
                "id": f"ltr_{int(datetime.now().timestamp() * 1000)}",
                "letter_no": letter_no,
                "date": today_jalali_str(),
                "title": normalize_honorifics(title or "گزارش رسمی"),
                "recipient": recipient or "مدیریت / واحد ذی‌ربط",
                "format": fmt.upper(),
                "path": str(file_path),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        data["letters"] = letters[:500]
        SUITE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_branding() -> dict[str, Any]:
    Config.ensure_directories()
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(DEFAULT_BRANDING)
    data["custom_fonts"] = []
    if BRANDING_FILE.exists():
        try:
            saved = json.loads(BRANDING_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
        except Exception:
            pass

    data["org_name"] = normalize_honorifics(data.get("org_name") or DEFAULT_BRANDING["org_name"])
    ft = normalize_honorifics(data.get("footer_text") or DEFAULT_BRANDING["footer_text"])
    if not ft or "عمار یاسر" in ft or "مرکز فعالیت‌های" in ft:
        ft = DEFAULT_BRANDING["footer_text"]
    data["footer_text"] = ft
    data["excel_default_title"] = normalize_honorifics(data.get("excel_default_title") or DEFAULT_BRANDING["excel_default_title"])

    raw_contact = str(data.get("contact_text") or "")
    phone_m = re.search(r"[۰-۹0-9]{2,4}[-–][۰-۹0-9]{6,8}(?:[-–][۰-۹0-9]{1,2})?", raw_contact)
    handle_m = re.search(r"@[A-Za-z0-9_]+", raw_contact)
    data["contact_phone"] = to_fa_digits(phone_m.group(0)) if phone_m else (data.get("contact_phone") or "۰۲۵-۳۷۷۲۵۲۲۵-۷")
    data["contact_handle"] = handle_m.group(0) if handle_m else (data.get("contact_handle") or "@emamhadi_qom")

    valid_fonts = []
    for item in data.get("custom_fonts") or []:
        if isinstance(item, dict) and item.get("name") and item.get("path") and Path(item["path"]).exists():
            valid_fonts.append({"name": str(item["name"]), "path": str(item["path"])})
    for fp in sorted(FONTS_DIR.glob("*")):
        if fp.suffix.lower() in (".ttf", ".otf", ".woff2") and not any(
            Path(x["path"]).resolve() == fp.resolve() for x in valid_fonts
        ):
            valid_fonts.append({"name": fp.stem, "path": str(fp)})
    data["custom_fonts"] = valid_fonts

    if data.get("logo_path") and not Path(data["logo_path"]).exists():
        data["logo_path"] = str(DEFAULT_LOGO_DEST) if DEFAULT_LOGO_DEST.exists() else ""
    return data


def save_branding(payload: dict[str, Any]) -> dict[str, Any]:
    Config.ensure_directories()
    cur = load_branding()
    allowed = (
        "org_name", "unit_name", "default_intro_text", "footer_text",
        "contact_phone", "contact_handle", "contact_text", "signature_title",
        "excel_default_title", "theme", "show_bismillah", "show_signature",
        "logo_path", "pdf_font", "word_font", "excel_font", "custom_fonts",
        "voice_engine", "voice_tts", "whisper_model", "ui_palette", "ui_density", "eitaa_templates", "ui_palette",
    )
    for k in allowed:
        if k in payload:
            val = payload[k]
            if isinstance(val, str) and k in ("org_name", "footer_text", "excel_default_title"):
                val = normalize_honorifics(val)
            cur[k] = val
    BRANDING_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


def install_logo_file(src_path: str) -> dict[str, Any]:
    p = Path(src_path)
    if not p.is_file():
        return {"ok": False, "error": "فایل لوگو یافت نشد."}
    DEFAULT_LOGO_DEST.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix.lower() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else ".png"
    dest = DEFAULT_LOGO_DEST.parent / f"logo{ext}"
    shutil.copy2(p, dest)
    updated = save_branding({"logo_path": str(dest)})
    return {"ok": True, "branding": updated, "logo_data_uri": get_logo_data_uri(str(dest))}


def install_font_file(src_path: str, custom_name: str | None = None) -> dict[str, Any]:
    p = Path(src_path)
    if not p.is_file():
        return {"ok": False, "error": "فایل فونت یافت نشد."}
    if p.suffix.lower() not in (".ttf", ".otf", ".woff2"):
        return {"ok": False, "error": "فقط فرمت‌های TTF، OTF و WOFF2 پشتیبانی می‌شوند."}
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    label = re.sub(r'[\\/*?:"<>|]', "", str(custom_name or p.stem)).strip() or p.stem
    dest = FONTS_DIR / f"{label}{p.suffix.lower()}"
    shutil.copy2(p, dest)
    cur = load_branding()
    fonts = [f for f in (cur.get("custom_fonts") or []) if f.get("name") != label]
    fonts.append({"name": label, "path": str(dest)})
    updated = save_branding({"custom_fonts": fonts, "pdf_font": label})
    return {"ok": True, "font_name": label, "branding": updated}


def get_logo_data_uri(logo_path: str) -> str:
    if not logo_path or not Path(logo_path).exists():
        return ""
    p = Path(logo_path)
    ext = p.suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext or 'png'}"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _build_font_face_css(branding: dict[str, Any]) -> str:
    rules = []
    for item in branding.get("custom_fonts") or []:
        fp = Path(item.get("path") or "")
        fname = str(item.get("name") or "").strip()
        if fname and fp.exists():
            ext = fp.suffix.lower().lstrip(".")
            fmt = "truetype" if ext == "ttf" else ("opentype" if ext == "otf" else "woff2")
            mime = "font/ttf" if ext == "ttf" else ("font/otf" if ext == "otf" else "font/woff2")
            b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
            safe_fn = fname.replace("'", "")
            rules.append(
                f"@font-face {{ font-family: '{safe_fn}'; src: url('data:{mime};base64,{b64}') format('{fmt}'); font-weight: 100 900; font-style: normal; }}"
            )
    return "\n".join(rules)


# ==================== ابزارهای راست‌چین دقیق Word ====================

def _init_rtl_normal_style(doc: Document, font_name: str):
    style = doc.styles["Normal"]
    style.font.name = font_name
    style.font.size = Pt(10.5)
    pPr = style._element.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "right")
    pPr.append(jc)
    rPr = style._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:cs", "w:ascii", "w:hAnsi", "w:eastAsia"):
        rFonts.set(qn(attr), font_name)
    rPr.append(OxmlElement("w:rtl"))


def _set_rtl_paragraph(p, jc_val: str = "right"):
    pPr = p._p.get_or_add_pPr()
    for tag in ("w:bidi", "w:jc"):
        old = pPr.find(qn(tag))
        if old is not None:
            pPr.remove(old)
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), jc_val)
    pPr.append(jc)


def _set_rtl_table(table):
    tblPr = table._tbl.tblPr
    if tblPr.find(qn("w:bidiVisual")) is None:
        tblPr.append(OxmlElement("w:bidiVisual"))


def _set_cell_bg(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>'))


def _set_cell_margins(cell, top=80, bottom=80, left=110, right=110):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        tcMar.append(el)
    tcPr.append(tcMar)


def _set_table_borders(table, color="CBD5E1"):
    tblPr = table._tbl.tblPr
    tblPr.append(
        parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'<w:left w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'<w:right w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
            f'</w:tblBorders>'
        )
    )


def _set_no_borders(table):
    tblPr = table._tbl.tblPr
    tblPr.append(
        parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            '<w:top w:val="none"/><w:bottom w:val="none"/>'
            '<w:left w:val="none"/><w:right w:val="none"/>'
            '<w:insideH w:val="none"/><w:insideV w:val="none"/>'
            '</w:tblBorders>'
        )
    )


def _add_fa_run(p, text: str, font_name: str = "Tahoma", size: float = 10.5, bold: bool = False, color_hex: str = "1E293B", ltr: bool = False):
    clean = to_fa_digits(normalize_honorifics(text)) if not ltr else str(text)
    run = p.add_run(clean)
    run.bold = bold
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color_hex)
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:cs", "w:ascii", "w:hAnsi", "w:eastAsia"):
        rFonts.set(qn(attr), font_name)
    if not ltr:
        rPr.append(OxmlElement("w:rtl"))
    szCs = OxmlElement("w:szCs")
    szCs.set(qn("w:val"), str(int(size * 2)))
    rPr.append(szCs)
    if bold:
        rPr.append(OxmlElement("w:bCs"))
    return run


def _add_inline_md(p, text: str, font_name: str = "Tahoma", size: float = 10.5, color_hex: str = "1E293B"):
    parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text or "")
    for seg in parts:
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**"):
            _add_fa_run(p, seg[2:-2], font_name=font_name, size=size, bold=True, color_hex=color_hex)
        elif seg.startswith("`") and seg.endswith("`"):
            _add_fa_run(p, seg[1:-1], font_name=font_name, size=max(8.5, size - 0.5), bold=True, color_hex="0F4C81", ltr=True)
        else:
            _add_fa_run(p, seg, font_name=font_name, size=size, bold=False, color_hex=color_hex)


def _add_styled_table(doc: Document, headers: list[str], rows: list[list[Any]], theme: dict[str, str], font_name: str):
    if not headers:
        return
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_rtl_table(tbl)
    _set_table_borders(tbl, "CBD5E1")

    for idx, h in enumerate(headers):
        cell = tbl.rows[0].cells[idx]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_cell_bg(cell, theme["primary"])
        _set_cell_margins(cell, 85, 85, 100, 100)
        p = cell.paragraphs[0]
        _set_rtl_paragraph(p, "center")
        _add_fa_run(p, str(h), font_name=font_name, size=9.5, bold=True, color_hex="FFFFFF")

    for r_idx, row in enumerate(rows):
        cells = tbl.rows[r_idx + 1].cells
        bg = theme["light"] if r_idx % 2 == 1 else "FFFFFF"
        for c_idx in range(len(headers)):
            val = row[c_idx] if c_idx < len(row) else ""
            cell = cells[c_idx]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_bg(cell, bg)
            _set_cell_margins(cell, 70, 70, 90, 90)
            p = cell.paragraphs[0]
            _set_rtl_paragraph(p, "right")
            _add_inline_md(p, str(val), font_name=font_name, size=9.2, color_hex="1E293B")

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)


def _save_data_uri_temp(data_uri: str) -> Path | None:
    if not data_uri or "," not in data_uri:
        return None
    try:
        header, b64 = data_uri.split(",", 1)
        ext = ".png" if "png" in header else ".jpg"
        tmp = Path(tempfile.gettempdir()) / f"ehadi_chart_{int(datetime.now().timestamp() * 1000000)}{ext}"
        tmp.write_bytes(base64.b64decode(b64))
        return tmp
    except Exception:
        return None


def export_official_docx(payload: dict[str, Any], dest_path: Path) -> str:
    branding = load_branding()
    theme = THEMES.get(branding.get("theme"), THEMES["emerald_beige"])
    word_font = str(branding.get("word_font") or "Tahoma").strip() or "Tahoma"
    letter_no = _next_letter_number()
    doc = Document()
    _init_rtl_normal_style(doc, word_font)

    for sec in doc.sections:
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(1.4)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(2.0)
        sec.right_margin = Cm(1.8)
        pgBorders = parse_xml(
            f'<w:pgBorders {nsdecls("w")} w:offsetFrom="page">'
            f'<w:left w:val="single" w:sz="48" w:space="0" w:color="{theme["primary"]}"/>'
            f'</w:pgBorders>'
        )
        sec._sectPr.append(pgBorders)

    if branding.get("show_bismillah", False):
        pb = doc.add_paragraph()
        pb.paragraph_format.space_after = Pt(4)
        _set_rtl_paragraph(pb, "center")
        _add_fa_run(pb, "بسم‌الله‌الرحمن‌الرحیم", font_name=word_font, size=11, bold=True, color_hex=theme["dark"])

    hdr_tbl = doc.add_table(rows=1, cols=3)
    hdr_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_rtl_table(hdr_tbl)
    _set_no_borders(hdr_tbl)

    c_right, c_mid, c_left = hdr_tbl.rows[0].cells
    c_right.width = Cm(3.8)
    c_mid.width = Cm(8.8)
    c_left.width = Cm(4.6)

    c_right.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p_logo = c_right.paragraphs[0]
    _set_rtl_paragraph(p_logo, "center")
    logo_p = branding.get("logo_path", "")
    if logo_p and Path(logo_p).exists():
        try:
            p_logo.add_run().add_picture(logo_p, width=Cm(2.9))
        except Exception:
            pass

    c_mid.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p_org = c_mid.paragraphs[0]
    _set_rtl_paragraph(p_org, "center")
    _add_fa_run(p_org, branding.get("org_name", ""), font_name=word_font, size=13.5, bold=True, color_hex=theme["primary"])
    p_unit = c_mid.add_paragraph()
    p_unit.paragraph_format.space_before = Pt(3)
    _set_rtl_paragraph(p_unit, "center")
    _add_fa_run(p_unit, branding.get("unit_name", ""), font_name=word_font, size=9.2, bold=True, color_hex=theme["dark"])

    has_attach = bool((payload.get("tables") or []) or (payload.get("citations") or []) or (payload.get("charts") or []))
    c_left.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    for lbl, val in (("تاریخ: ", today_jalali_str()), ("شماره: ", letter_no), ("پیوست: ", "دارد" if has_attach else "ندارد")):
        pm = c_left.paragraphs[0] if lbl.startswith("تاریخ") else c_left.add_paragraph()
        pm.paragraph_format.space_after = Pt(2)
        _set_rtl_paragraph(pm, "right")
        _add_fa_run(pm, lbl, font_name=word_font, size=9.2, bold=True, color_hex=theme["primary"])
        _add_fa_run(pm, val, font_name=word_font, size=9.2, bold=False, color_hex="1E293B")

    sep_p = doc.add_paragraph()
    sep_p.paragraph_format.space_before = Pt(4)
    sep_p.paragraph_format.space_after = Pt(10)
    sep_p._p.get_or_add_pPr().append(
        parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="14" w:space="1" w:color="{theme["primary"]}"/></w:pBdr>')
    )

    title_txt = normalize_honorifics(str(payload.get("title") or branding.get("excel_default_title") or "گزارش رسمی").strip())
    pt = doc.add_paragraph()
    pt.paragraph_format.space_after = Pt(7)
    _set_rtl_paragraph(pt, "right")
    _add_fa_run(pt, "موضوع: ", font_name=word_font, size=11, bold=True, color_hex=theme["primary"])
    _add_fa_run(pt, title_txt, font_name=word_font, size=11, bold=True, color_hex=theme["dark"])

    intro_txt = str(payload.get("intro_text") if "intro_text" in payload else (branding.get("default_intro_text") or "")).strip()
    if intro_txt:
        pi = doc.add_paragraph()
        pi.paragraph_format.space_after = Pt(8)
        pi.paragraph_format.line_spacing = 1.4
        _set_rtl_paragraph(pi, "both")
        _add_fa_run(pi, intro_txt, font_name=word_font, size=10.2, color_hex="1E293B")

    kpis = payload.get("kpis") or []
    if kpis:
        for start in range(0, len(kpis), 4):
            chunk = kpis[start:start + 4]
            kt = doc.add_table(rows=1, cols=len(chunk))
            kt.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_rtl_table(kt)
            _set_table_borders(kt, theme["accent"])
            for idx, kp in enumerate(chunk):
                cell = kt.rows[0].cells[idx]
                _set_cell_bg(cell, theme["light"])
                _set_cell_margins(cell, 85, 85, 80, 80)
                ka = cell.paragraphs[0]
                _set_rtl_paragraph(ka, "center")
                _add_fa_run(ka, str(kp.get("label", "")), font_name=word_font, size=8.5, color_hex="475569")
                kb = cell.add_paragraph()
                _set_rtl_paragraph(kb, "center")
                _add_fa_run(kb, str(kp.get("value", "")), font_name=word_font, size=11, bold=True, color_hex=theme["dark"])
            doc.add_paragraph()

    tmp_imgs = []
    for ch in payload.get("charts") or []:
        img_p = _save_data_uri_temp(ch.get("data_uri") or "")
        if img_p and img_p.exists():
            tmp_imgs.append(img_p)
            cp = doc.add_paragraph()
            cp.paragraph_format.space_before = Pt(8)
            cp.paragraph_format.space_after = Pt(3)
            _set_rtl_paragraph(cp, "right")
            _add_fa_run(cp, str(ch.get("title") or "نمودار تحلیلی"), font_name=word_font, size=10.5, bold=True, color_hex=theme["dark"])
            ip = doc.add_paragraph()
            ip.paragraph_format.space_after = Pt(8)
            _set_rtl_paragraph(ip, "center")
            try:
                ip.add_run().add_picture(str(img_p), width=Cm(16.2))
            except Exception:
                pass

    content = str(payload.get("content") or "").replace("\r\n", "\n")
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or re.fullmatch(r"-{3,}", line):
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?[\s:-]+\|[\s|:-]*$", lines[i + 1].strip()):
            split_row = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            headers = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            _add_styled_table(doc, headers, rows, theme, word_font)
            continue
        if line.startswith("### "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)
            _set_rtl_paragraph(p, "right")
            _add_fa_run(p, line[4:], font_name=word_font, size=10.8, bold=True, color_hex=theme["primary"])
        elif line.startswith("## ") or line.startswith("# "):
            txt = line[3:] if line.startswith("## ") else line[2:]
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            _set_rtl_paragraph(p, "right")
            _add_fa_run(p, txt, font_name=word_font, size=11.5, bold=True, color_hex=theme["dark"])
        elif re.match(r"^[-*•]\s+", line):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            _set_rtl_paragraph(p, "right")
            _add_inline_md(p, "•  " + re.sub(r"^[-*•]\s+", "", line), font_name=word_font, size=10.1)
        elif re.match(r"^\d+[.)]\s+", line):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            _set_rtl_paragraph(p, "right")
            _add_inline_md(p, line, font_name=word_font, size=10.1)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(5)
            p.paragraph_format.line_spacing = 1.4
            _set_rtl_paragraph(p, "both")
            _add_inline_md(p, line, font_name=word_font, size=10.2)
        i += 1

    for tbl in payload.get("tables") or []:
        cols = tbl.get("columns") or []
        rows = (tbl.get("rows") or [])[:150]
        if cols and rows:
            tp = doc.add_paragraph()
            tp.paragraph_format.space_before = Pt(8)
            tp.paragraph_format.space_after = Pt(4)
            _set_rtl_paragraph(tp, "right")
            _add_fa_run(tp, str(tbl.get("title") or "جدول داده‌ها"), font_name=word_font, size=10.8, bold=True, color_hex=theme["dark"])
            _add_styled_table(doc, cols, rows, theme, word_font)

    citations = payload.get("citations") or []
    if citations:
        cp = doc.add_paragraph()
        cp.paragraph_format.space_before = Pt(10)
        _set_rtl_paragraph(cp, "right")
        _add_fa_run(cp, "پیوست‌ها و منابع استنادشده:", font_name=word_font, size=9.8, bold=True, color_hex=theme["primary"])
        for c in citations:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            _set_rtl_paragraph(p, "right")
            _add_fa_run(p, f"▪ {c.get('file_name', '')} — {c.get('location', '')}", font_name=word_font, size=8.8, color_hex="475569")

    if branding.get("show_signature", True):
        sig_p = doc.add_paragraph()
        sig_p.paragraph_format.space_before = Pt(22)
        _set_rtl_paragraph(sig_p, "left")
        _add_fa_run(sig_p, str(branding.get("signature_title") or "با تشکر و احترام — مدیریت مؤسسه"), font_name=word_font, size=9.8, bold=True, color_hex=theme["dark"])
        sig_l = doc.add_paragraph()
        _set_rtl_paragraph(sig_l, "left")
        _add_fa_run(sig_l, "..............................................", font_name=word_font, size=9.2, color_hex="94A3B8")

    footer_p = doc.sections[0].footer.paragraphs[0]
    _set_rtl_paragraph(footer_p, "center")
    _add_fa_run(footer_p, branding.get("footer_text", f"مؤسسه علمی فرهنگی امام هادی{HONORIFIC_AS}"), font_name=word_font, size=8.4, bold=True, color_hex=theme["primary"])
    _add_fa_run(footer_p, "   |   تلفن: ", font_name=word_font, size=8.4, color_hex=theme["dark"])
    _add_fa_run(footer_p, "\u200e" + branding.get("contact_phone", "۰۲۵-۳۷۷۲۵۲۲۵-۷") + "\u200e", font_name=word_font, size=8.4, bold=True, color_hex=theme["primary"], ltr=True)
    _add_fa_run(footer_p, "   |   ", font_name=word_font, size=8.4, color_hex=theme["dark"])
    _add_fa_run(footer_p, "\u200e" + branding.get("contact_handle", "@emamhadi_qom") + "\u200e", font_name=word_font, size=8.4, bold=True, color_hex=theme["primary"], ltr=True)

    doc.save(dest_path)
    for im in tmp_imgs:
        try:
            im.unlink(missing_ok=True)
        except Exception:
            pass
    register_exported_letter(title_txt, "DOCX", str(dest_path), letter_no, str(payload.get("recipient") or ""))
    return str(dest_path)


def _esc(s: Any) -> str:
    txt = normalize_honorifics(str(s or ""))
    txt = to_fa_digits(txt)
    txt = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    txt = txt.replace(HONORIFIC_AS, f'<span class="honorific">{HONORIFIC_AS}</span>')
    return txt


def _esc_ltr(s: Any, fa_digits: bool = False) -> str:
    txt = to_fa_digits(str(s or "")) if fa_digits else str(s or "")
    return txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _inline_html(s: str) -> str:
    t = _esc(s)
    t = re.sub(r"`([^`]+)`", r"<bdi dir='ltr'><code>\1</code></bdi>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    return t


def _md_to_html(md_text: str) -> str:
    lines = str(md_text or "").replace("\r\n", "\n").split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if re.fullmatch(r"-{3,}", line):
            out.append("<hr class='sec-div'/>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?[\s:-]+\|[\s|:-]*$", lines[i + 1].strip()):
            split_row = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            headers = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            ths = "".join(f"<th>{_inline_html(h)}</th>" for h in headers)
            trs = "".join("<tr>" + "".join(f"<td>{_inline_html(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<div class='tbl-wrap'><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>")
            continue
        if line.startswith("### "):
            out.append(f"<h4>{_inline_html(line[4:])}</h4>")
        elif line.startswith("## ") or line.startswith("# "):
            out.append(f"<h3>{_inline_html(line[3:] if line.startswith('## ') else line[2:])}</h3>")
        elif re.match(r"^[-*•]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*•]\s+", lines[i].strip()):
                items.append(f"<li>{_inline_html(re.sub(r'^[-*•]\s+', '', lines[i].strip()))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif re.match(r"^\d+[.)]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                items.append(f"<li>{_inline_html(re.sub(r'^\d+[.)]\s+', '', lines[i].strip()))}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        else:
            out.append(f"<p>{_inline_html(line)}</p>")
        i += 1
    return "\n".join(out)


def _find_chromium_browser() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which("msedge") or shutil.which("chrome")


def _render_html_to_pdf(html_doc: str, dest_path: Path) -> dict[str, Any]:
    browser = _find_chromium_browser()
    tmp_html = Path(tempfile.gettempdir()) / f"ehadi_report_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.html"
    tmp_html.write_text(html_doc, encoding="utf-8")
    if browser:
        try:
            cmd = [
                browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={str(dest_path)}", tmp_html.as_uri(),
            ]
            subprocess.run(cmd, check=True, timeout=30, creationflags=0x08000000)
            if dest_path.exists() and dest_path.stat().st_size > 1000:
                try:
                    tmp_html.unlink(missing_ok=True)
                except Exception:
                    pass
                return {"ok": True, "path": str(dest_path), "mode": "pdf"}
        except Exception:
            pass
    os.startfile(str(tmp_html))
    return {"ok": True, "path": str(tmp_html), "mode": "html_print"}


def _build_pdf_shell(branding: dict[str, Any], theme: dict[str, str], title: str, letter_no: str, has_attach: bool, inner_html: str) -> str:
    font_face_css = _build_font_face_css(branding)
    chosen_font = str(branding.get("pdf_font") or "Vazirmatn").strip() or "Vazirmatn"
    font_stack = f"'{chosen_font.replace(chr(39), '')}', 'Vazirmatn', 'IRANSans', 'Tahoma', sans-serif"
    logo_uri = get_logo_data_uri(branding.get("logo_path", ""))
    logo_img = f'<img src="{logo_uri}" class="logo-img" alt="لوگوی مؤسسه"/>' if logo_uri else '<span class="logo-fallback">لوگو</span>'
    bismillah_html = '<div class="bismillah">بسم‌الله‌الرحمن‌الرحیم</div>' if branding.get("show_bismillah", False) else ""

    p_hex, d_hex, a_hex, as_hex, l_hex, pill_hex = (
        theme["primary"], theme["dark"], theme["accent"], theme["accent_soft"], theme["light"], theme["pill_bg"]
    )
    phone_str = _esc_ltr(branding.get("contact_phone") or "۰۲۵-۳۷۷۲۵۲۲۵-۷", fa_digits=True)
    handle_str = _esc_ltr(branding.get("contact_handle") or "@emamhadi_qom", fa_digits=False)

    geo_svg = f"""
    <svg class="geo-frame-svg" viewBox="0 0 794 1123" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
      <rect x="0" y="0" width="34" height="1123" fill="#{p_hex}"/>
      <polygon points="0,0 310,0 278,32 0,32" fill="#{p_hex}"/>
      <polygon points="34,32 266,32 248,50 83,50 83,190 34,239" fill="#{a_hex}"/>
      <polygon points="0,126 60,66 60,152 0,212" fill="#{a_hex}"/>
      <polyline points="34,32 62,60 62,150 34,178" fill="none" stroke="#FFFFFF" stroke-width="4.5"/>
      <polygon points="34,925 82,877 82,1065 34,1113" fill="#{a_hex}"/>
      <polyline points="34,1118 90,1062 574,1062" fill="none" stroke="#{p_hex}" stroke-width="2.2"/>
      <polygon points="622,1062 794,1062 794,1123 564,1123" fill="#{a_hex}"/>
    </svg>
    """

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8"/>
<title>{_esc(title)}</title>
<style>
  {font_face_css}
  @page {{ size: A4; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{
    direction: rtl; text-align: right; font-family: {font_stack};
    color: #1e293b; background: #ffffff; margin: 0; padding: 0; font-size: 9.8pt; line-height: 1.85;
  }}
  .honorific {{ font-family: 'Amiri', 'Vazirmatn', 'Tahoma', serif; font-size: 1.12em; font-weight: 700; display: inline; }}
  .ltr-iso {{ direction: ltr; unicode-bidi: isolate; display: inline-block; }}
  .geo-frame-svg {{ position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; }}
  .page-canvas {{ position: relative; z-index: 1; padding: 14mm 18mm 26mm 28mm; }}
  .bismillah {{ text-align: center; font-weight: 700; font-size: 10.5pt; color: #{d_hex}; margin-bottom: 4px; }}
  .letterhead {{ display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 14px; padding-bottom: 10px; margin-bottom: 12px; }}
  .lh-logo-col {{ width: 98px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
  .lh-logo-diamond-outer {{ width: 74px; height: 74px; background: #{p_hex}; transform: rotate(45deg); display: flex; align-items: center; justify-content: center; border-radius: 4px; }}
  .lh-logo-diamond-inner {{ width: 54px; height: 54px; background: #{as_hex}; display: flex; align-items: center; justify-content: center; border-radius: 3px; }}
  .logo-img {{ transform: rotate(-45deg); max-width: 64px; max-height: 50px; object-fit: contain; }}
  .logo-fallback {{ transform: rotate(-45deg); font-size: 8.5pt; font-weight: 700; color: #{d_hex}; }}
  .lh-center {{ flex: 1; text-align: center; padding: 0 8px; }}
  .lh-org {{ font-size: 14pt; font-weight: 800; color: #{p_hex}; line-height: 1.5; }}
  .lh-unit-pill {{ display: inline-block; margin-top: 4px; padding: 2px 15px; border-radius: 999px; background: #{pill_hex}; color: #{d_hex}; font-size: 8.6pt; font-weight: 700; }}
  .lh-meta {{ min-width: 132px; direction: rtl; text-align: right; font-size: 8.9pt; color: #1e293b; line-height: 1.8; }}
  .lh-meta-lbl {{ color: #{p_hex}; font-weight: 700; margin-left: 4px; }}
  .subject-bar {{ direction: rtl; text-align: right; background: #{l_hex}; border-right: 4px solid #{p_hex}; border-radius: 6px; padding: 6px 12px; margin: 2px 0 10px; font-size: 10.2pt; font-weight: 700; color: #{d_hex}; }}
  .letter-intro {{ direction: rtl; text-align: justify; text-align-last: right; font-size: 9.5pt; color: #1e293b; margin: 0 0 10px; padding-bottom: 7px; border-bottom: 1px dashed #{a_hex}; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }}
  .kpi {{ background: #{l_hex}; border: 1px solid #{a_hex}; border-radius: 8px; padding: 7px 9px; text-align: center; }}
  .kpi-l {{ font-size: 8pt; color: #475569; }}
  .kpi-v {{ font-size: 11pt; font-weight: 800; color: #{d_hex}; margin-top: 2px; }}
  .chart-card {{ page-break-inside: avoid; margin: 10px 0 14px; padding: 10px; border: 1px solid #{a_hex}; border-radius: 8px; background: #ffffff; }}
  .chart-card-title {{ font-size: 9.5pt; font-weight: 700; color: #{d_hex}; margin-bottom: 6px; text-align: right; }}
  .chart-card img {{ width: 100%; height: auto; max-height: 78mm; object-fit: contain; display: block; margin: 0 auto; }}
  h3 {{ direction: rtl; text-align: right; color: #{d_hex}; font-size: 10.8pt; margin: 10px 0 5px; }}
  h4 {{ direction: rtl; text-align: right; color: #{p_hex}; font-size: 9.8pt; margin: 8px 0 3px; }}
  p {{ direction: rtl; text-align: justify; text-align-last: right; margin: 4px 0; color: #1e293b; }}
  ul, ol {{ direction: rtl; text-align: right; margin: 4px 0 8px; padding-right: 20px; padding-left: 0; }}
  li {{ direction: rtl; text-align: right; margin-bottom: 2px; }}
  code {{ background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 8.6pt; color: #0f172a; }}
  .tbl-wrap {{ width: 100%; margin: 6px 0 12px; }}
  table {{ direction: rtl; width: 100%; border-collapse: collapse; font-size: 8.6pt; page-break-inside: auto; }}
  tr {{ page-break-inside: avoid; }}
  th {{ background: #{p_hex}; color: #ffffff; font-weight: 700; padding: 5.5px 7px; border: 1px solid #cbd5e1; text-align: center; }}
  td {{ padding: 5.5px 7px; border: 1px solid #cbd5e1; text-align: right; color: #1e293b; }}
  td.center {{ text-align: center; }}
  tbody tr:nth-child(even) {{ background: #{l_hex}; }}
  .cites {{ direction: rtl; text-align: right; margin-top: 12px; padding: 8px 12px; border-radius: 6px; background: #{l_hex}; border-right: 3px solid #{p_hex}; font-size: 8.4pt; color: #334155; }}
  .cites-title {{ font-weight: 700; color: #{d_hex}; margin-bottom: 3px; }}
  .sig-area {{ display: flex; justify-content: flex-end; margin-top: 18px; page-break-inside: avoid; }}
  .sig-card {{ min-width: 195px; text-align: center; }}
  .sig-lbl {{ font-size: 9.2pt; font-weight: 700; color: #{d_hex}; }}
  .sig-line {{ margin-top: 30px; border-bottom: 1.5px dashed #{a_hex}; }}
  .letter-footer {{
    position: fixed; bottom: 5.5mm; left: 26mm; right: 60mm;
    display: flex; flex-direction: row; align-items: center; justify-content: space-between;
    gap: 10px; font-size: 8.4pt; color: #{p_hex}; font-weight: 700; z-index: 2;
  }}
  .footer-right {{ white-space: nowrap; color: #{p_hex}; }}
  .footer-left {{ display: flex; align-items: center; gap: 10px; white-space: nowrap; }}
  .footer-sep {{ width: 1.5px; height: 18px; background: #{a_hex}; flex-shrink: 0; }}
  .footer-icon {{
    width: 22px; height: 22px; border-radius: 5px; background: #{p_hex}; color: #ffffff;
    display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
  }}
</style>
</head>
<body>
  {geo_svg}
  <div class="page-canvas">
    {bismillah_html}
    <div class="letterhead">
      <div class="lh-logo-col">
        <div class="lh-logo-diamond-outer"><div class="lh-logo-diamond-inner">{logo_img}</div></div>
      </div>
      <div class="lh-center">
        <div class="lh-org">{_esc(branding.get('org_name'))}</div>
        <div class="lh-unit-pill">{_esc(branding.get('unit_name'))}</div>
      </div>
      <div class="lh-meta">
        <div><span class="lh-meta-lbl">تاریخ:</span><span class="ltr-iso">{today_jalali_str()}</span></div>
        <div><span class="lh-meta-lbl">شماره:</span><span class="ltr-iso">{letter_no}</span></div>
        <div><span class="lh-meta-lbl">پیوست:</span><span>{"دارد" if has_attach else "ندارد"}</span></div>
      </div>
    </div>
    {inner_html}
  </div>

  <div class="letter-footer">
    <span class="footer-right">{_esc(branding.get('footer_text'))}</span>
    <span class="footer-left">
      <span class="footer-sep"></span>
      <span>تلفن: <span class="ltr-iso">{phone_str}</span></span>
      <span class="footer-sep"></span>
      <span class="ltr-iso">{handle_str}</span>
      <span class="footer-icon">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
        </svg>
      </span>
    </span>
  </div>
</body>
</html>"""


def export_official_pdf(payload: dict[str, Any], dest_path: Path) -> dict[str, Any]:
    branding = load_branding()
    theme = THEMES.get(branding.get("theme"), THEMES["emerald_beige"])
    letter_no = _next_letter_number()
    title = normalize_honorifics(str(payload.get("title") or branding.get("excel_default_title") or "گزارش رسمی").strip())
    intro_txt = str(payload.get("intro_text") if "intro_text" in payload else (branding.get("default_intro_text") or "")).strip()
    has_attach = bool((payload.get("tables") or []) or (payload.get("citations") or []) or (payload.get("charts") or []))

    kpis_html = ""
    kpis = payload.get("kpis") or []
    if kpis:
        cards = "".join(f'<div class="kpi"><div class="kpi-l">{_esc(k.get("label"))}</div><div class="kpi-v">{_esc(k.get("value"))}</div></div>' for k in kpis)
        kpis_html = f'<div class="kpi-grid">{cards}</div>'

    charts_html = ""
    for ch in payload.get("charts") or []:
        if ch.get("data_uri"):
            charts_html += f'<div class="chart-card"><div class="chart-card-title">{_esc(ch.get("title") or "نمودار")}</div><img src="{ch["data_uri"]}" alt="chart"/></div>'

    intro_html = f'<p class="letter-intro">{_inline_html(intro_txt)}</p>' if intro_txt else ""
    body_html = _md_to_html(payload.get("content") or "")

    tables_html = ""
    for tbl in payload.get("tables") or []:
        cols = tbl.get("columns") or []
        rows = (tbl.get("rows") or [])[:180]
        if cols and rows:
            ths = "".join(f"<th>{_esc(c)}</th>" for c in cols)
            trs = "".join("<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in r) + "</tr>" for r in rows)
            tables_html += f'<h3>{_esc(tbl.get("title") or "جدول داده‌ها")}</h3><div class="tbl-wrap"><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>'

    cites_html = ""
    cites = payload.get("citations") or []
    if cites:
        lis = "".join(f"<li>{_esc(c.get('file_name'))} — {_esc(c.get('location'))}</li>" for c in cites)
        cites_html = f'<div class="cites"><div class="cites-title">پیوست‌ها و منابع استنادشده:</div><ul>{lis}</ul></div>'

    sig_html = (
        f'<div class="sig-area"><div class="sig-card"><div class="sig-lbl">{_esc(branding.get("signature_title") or "با تشکر و احترام — مدیریت مؤسسه")}</div><div class="sig-line"></div></div></div>'
        if branding.get("show_signature", True)
        else ""
    )

    inner = f'<div class="subject-bar">موضوع: {_esc(title)}</div>{intro_html}{kpis_html}{charts_html}{body_html}{tables_html}{cites_html}{sig_html}'
    html_doc = _build_pdf_shell(branding, theme, title, letter_no, has_attach, inner)
    res = _render_html_to_pdf(html_doc, dest_path)
    if res.get("ok"):
        register_exported_letter(title, "PDF", res["path"], letter_no, str(payload.get("recipient") or ""))
    return res


def export_attendance_sheet_pdf(payload: dict[str, Any], dest_path: Path) -> dict[str, Any]:
    branding = load_branding()
    theme = THEMES.get(branding.get("theme"), THEMES["emerald_beige"])
    letter_no = _next_letter_number()
    course = str(payload.get("course_title") or "دوره آموزشی").strip()
    teacher = str(payload.get("teacher") or "").strip()
    group = str(payload.get("group") or "").strip()
    sessions = max(1, min(10, int(payload.get("sessions_count") or 6)))
    rows = payload.get("participants") or []

    sess_headers = "".join(f"<th>جلسه {to_fa_digits(str(i))}</th>" for i in range(1, sessions + 1))
    body_rows = []
    for idx, p in enumerate(rows, 1):
        name = _esc(p.get("name") or "")
        level = _esc(p.get("level") or "—")
        phone = _esc_ltr(p.get("phone") or "—", fa_digits=True)
        tag = "جدید" if p.get("is_new") else "قدیمی"
        checks = "".join('<td class="center"></td>' for _ in range(sessions))
        body_rows.append(
            f'<tr><td class="center">{to_fa_digits(str(idx))}</td><td><strong>{name}</strong></td>'
            f'<td class="center">{level}</td><td class="center"><span class="ltr-iso">{phone}</span></td>'
            f'<td class="center">{tag}</td>{checks}</tr>'
        )

    meta_line = "  |  ".join(x for x in [
        f"کارگروه: {group}" if group else "",
        f"استاد: {teacher}" if teacher else "",
        f"تعداد ثبت‌نامی: {to_fa_digits(str(len(rows)))} نفر",
    ] if x)

    inner = (
        f'<div class="subject-bar">لیست رسمی حضور و غیاب: {_esc(course)}</div>'
        f'<p class="letter-intro">{_esc(meta_line)}</p>'
        f'<div class="tbl-wrap"><table><thead><tr>'
        f'<th style="width:28px;">ردیف</th><th>نام و نام خانوادگی</th><th style="width:65px;">سطح</th>'
        f'<th style="width:92px;">شماره تماس</th><th style="width:48px;">سابقه</th>{sess_headers}'
        f'</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'
        f'<div class="sig-area"><div class="sig-card"><div class="sig-lbl">تأیید دبیر دوره / مسئول آموزش</div><div class="sig-line"></div></div></div>'
    )
    html_doc = _build_pdf_shell(branding, theme, f"لیست حضور و غیاب — {course}", letter_no, False, inner)
    res = _render_html_to_pdf(html_doc, dest_path)
    if res.get("ok"):
        register_exported_letter(f"برگه حضور و غیاب — {course}", "PDF", res["path"], letter_no, teacher or "واحد آموزش")
    return res


def export_analytics_excel(analytics: dict[str, Any], dest_path: Path) -> dict[str, Any]:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except Exception as exc:
        return {"ok": False, "error": f"کتابخانه openpyxl در دسترس نیست: {exc}"}

    branding = load_branding()
    ef = str(branding.get("excel_font") or "Tahoma").strip() or "Tahoma"
    wb = Workbook()

    hdr_fill = PatternFill("solid", fgColor="0B8443")
    hdr_font = Font(name=ef, size=10, bold=True, color="FFFFFF")
    body_font = Font(name=ef, size=10, color="1E293B")
    alt_fill = PatternFill("solid", fgColor="F4F8F5")

    def style_sheet(ws, headers: list[str], rows: list[list[Any]]):
        ws.views.sheetView[0].rightToLeft = True
        ws.append(headers)
        for col_i in range(1, len(headers) + 1):
            c = ws.cell(row=1, column=col_i)
            c.fill = hdr_fill
            c.font = hdr_font
            c.alignment = Alignment(horizontal="center", vertical="center")
        for r_i, row in enumerate(rows, 2):
            ws.append(row)
            for col_i in range(1, len(headers) + 1):
                c = ws.cell(row=r_i, column=col_i)
                c.font = body_font
                c.alignment = Alignment(horizontal="right", vertical="center")
                if r_i % 2 == 1:
                    c.fill = alt_fill
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(45, max(12, max_len + 5))

    ws1 = wb.active
    ws1.title = "خلاصه شاخص‌ها"
    k = analytics.get("kpis") or {}
    style_sheet(
        ws1,
        ["شاخص مدیریتی", "مقدار"],
        [
            ["تعداد کل دوره‌ها و رویدادها", k.get("total_courses", 0)],
            ["مجموع شرکت‌کنندگان (کل حضور)", k.get("total_attendance", 0)],
            ["شرکت‌کنندگان یکتا (غیرتکراری)", k.get("unique_participants", 0)],
            ["نرخ بازگشت و وفاداری (%)", k.get("repeat_rate", 0)],
            ["میانگین شرکت‌کننده در هر دوره", k.get("avg_per_course", 0)],
            ["تعداد اساتید فعال", k.get("total_teachers", 0)],
            ["تعداد کارگروه‌ها", k.get("total_groups", 0)],
            ["مجموع هزینه‌ها (تومان)", k.get("total_cost", 0)],
            ["هزینه به ازای هر مخاطب (تومان)", k.get("cost_per_attendee", 0)],
            ["امتیاز سلامت داده‌ها (%)", k.get("data_health_score", 100)],
        ],
    )

    ws2 = wb.create_sheet("تفکیک کارگروه‌ها")
    style_sheet(
        ws2,
        ["کارگروه", "تعداد دوره‌ها", "مجموع حضور", "شرکت‌کنندگان یکتا", "میانگین هر دوره", "نرخ بازگشت (%)", "هزینه (تومان)"],
        [
            [g["name"], g["courses"], g["attendance"], g["unique"], g["avg_attendance"], g["repeat_rate"], g["cost"]]
            for g in (analytics.get("groups") or [])
        ],
    )

    ws3 = wb.create_sheet("عملکرد اساتید")
    style_sheet(
        ws3,
        ["نام استاد", "تعداد دوره‌ها", "مجموع مخاطبان", "مخاطبان یکتا", "میانگین جذب", "کارگروه‌ها"],
        [
            [t["name"], t["courses"], t["attendance"], t["unique"], t["avg_attendance"], "، ".join(t.get("groups") or [])]
            for t in (analytics.get("teachers") or [])
        ],
    )

    ws4 = wb.create_sheet("مخاطبان یکتا")
    style_sheet(
        ws4,
        ["نام و نام خانوادگی", "شماره تماس", "سطح", "تعداد دوره‌ها", "وضعیت وفاداری", "کارگروه‌ها", "عناوین دوره‌ها"],
        [
            [
                p["name"],
                p.get("phone") or "—",
                p.get("level") or "—",
                p.get("courses_count", 1),
                p.get("loyalty") or "جدید",
                "، ".join(p.get("groups") or []),
                " | ".join(p.get("courses") or []),
            ]
            for p in (analytics.get("participants") or [])
        ],
    )

    wb.save(dest_path)
    return {"ok": True, "path": str(dest_path)}


def format_teacher_short(raw: str) -> str:
    s = str(raw or "").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u0623", "\u0627").replace("\u0625", "\u0627")
    s = re.sub(r"[\u200c\u200f\u200e]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(\.{2,}|\u2026)+$", "", s).strip()
    if not s:
        return "\u0646\u0627\u0645\u0634\u062e\u0635"
    collective = (
        "\u062c\u0645\u0639\u06cc \u0627\u0632", "\u06af\u0631\u0648\u0647\u06cc \u0627\u0632",
        "\u062c\u0645\u0639\u06cc", "\u06af\u0631\u0648\u0647\u06cc",
        "\u0627\u0633\u0627\u062a\u06cc\u062f", "\u0646\u0634\u0633\u062a",
        "\u0647\u0645\u0627\u06cc\u0634", "\u0646\u0627\u0634\u0646\u0627\u0633", "\u0646\u0627\u0645\u0634\u062e\u0635"
    )
    if any(k in s for k in collective):
        return s
    first_names = {
        "\u0631\u0636\u0627", "\u0645\u062d\u0645\u062f", "\u0639\u0644\u06cc", "\u062d\u0633\u06cc\u0646",
        "\u062d\u0633\u0646", "\u0645\u0647\u062f\u06cc", "\u0627\u062d\u0645\u062f", "\u0645\u062d\u0645\u0648\u062f",
        "\u0645\u0635\u0637\u0641\u06cc", "\u0645\u0631\u062a\u0636\u06cc", "\u0645\u062c\u062a\u0628\u06cc",
        "\u062c\u0648\u0627\u062f", "\u06a9\u0627\u0638\u0645", "\u0635\u0627\u062f\u0642", "\u0628\u0627\u0642\u0631",
        "\u062a\u0642\u06cc", "\u0646\u0642\u06cc", "\u0627\u06a9\u0628\u0631", "\u0627\u0635\u063a\u0631",
        "\u0639\u0628\u0627\u0633", "\u0645\u0633\u0639\u0648\u062f", "\u0633\u0639\u06cc\u062f", "\u0645\u062c\u06cc\u062f",
        "\u062d\u0645\u06cc\u062f", "\u0648\u062d\u06cc\u062f", "\u062f\u0627\u0648\u062f", "\u062f\u0627\u0648\u0648\u062f",
        "\u0631\u0633\u0648\u0644", "\u0646\u0627\u0635\u0631", "\u0645\u0646\u0635\u0648\u0631", "\u0645\u062d\u0633\u0646",
        "\u062d\u0627\u0645\u062f", "\u0627\u0645\u06cc\u0631", "\u0627\u0628\u0631\u0627\u0647\u06cc\u0645",
        "\u0627\u0633\u0645\u0627\u0639\u06cc\u0644", "\u06cc\u0648\u0633\u0641", "\u062c\u0639\u0641\u0631",
        "\u0647\u0627\u062f\u06cc", "\u062d\u0628\u06cc\u0628", "\u06a9\u0631\u06cc\u0645", "\u0631\u062d\u06cc\u0645",
        "\u0642\u0627\u0633\u0645", "\u062c\u0644\u0627\u0644", "\u062c\u0645\u0627\u0644", "\u06a9\u0645\u0627\u0644",
        "\u0645\u0638\u0647\u0631", "\u062d\u0645\u06cc\u062f\u0631\u0636\u0627", "\u0639\u0644\u06cc\u0631\u0636\u0627",
        "\u0645\u062d\u0645\u062f\u0631\u0636\u0627", "\u0645\u062d\u0645\u062f\u062d\u0633\u06cc\u0646",
        "\u0645\u062d\u0645\u062f\u0645\u0647\u062f\u06cc", "\u0645\u062d\u0645\u062f\u062c\u0648\u0627\u062f",
        "\u0645\u062d\u0645\u062f\u0639\u0644\u06cc", "\u0627\u0645\u06cc\u0631\u062d\u0633\u06cc\u0646"
    }
    rx = re.compile(
        r"^(?:\u062d\u062c\u062a\s*\u0627\u0644\u0627\u0633\u0644\u0627\u0645(?:\s*\u0648\s*\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646)?|"
        r"\u062d\u062c\u062c\s*\u0627\u0644\u0627\u0633\u0644\u0627\u0645(?:\s*\u0648\s*\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646)?|"
        r"\u0648\s*\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646|\u0622\u06cc\u062a\s*\u0627\u0644\u0644\u0647(?:\s*\u0627\u0644\u0639\u0638\u0645\u06cc)?|"
        r"\u062f\u06a9\u062a\u0631|\u0645\u0647\u0646\u062f\u0633|\u062c\u0646\u0627\u0628\s*\u0622\u0642\u0627\u06cc|\u0622\u0642\u0627\u06cc|"
        r"\u0633\u0631\u06a9\u0627\u0631\s*\u062e\u0627\u0646\u0645|\u062e\u0627\u0646\u0645|\u0627\u0633\u062a\u0627\u062f|\u0634\u06cc\u062e|\u0633\u06cc\u062f\u0647|\u0633\u06cc\u062f|\u062d\u0627\u062c)[\s:\-\u2013\u2014]+"
    )
    def clean_one(p: str) -> str:
        p = p.strip()
        for _ in range(6):
            nxt = rx.sub("", p).strip()
            if nxt == p:
                break
            p = nxt
        words = [w for w in p.split() if w]
        for _ in range(3):
            if len(words) < 2:
                break
            w0 = words[0]
            if w0 in first_names:
                words.pop(0)
                continue
            if w0.startswith("\u0633\u06cc\u062f") and len(w0) > 4:
                rest = w0[4:] if w0.startswith("\u0633\u06cc\u062f\u0647") else w0[3:]
                if rest in first_names:
                    words.pop(0)
                    continue
            break
        return " ".join(words).strip()

    s2 = re.sub(r"\s+(?=(?:\u062d\u062c\u062a|\u062d\u062c\u062c|\u0622\u06cc\u062a|\u062f\u06a9\u062a\u0631)\s)", " / ", s)
    parts = [clean_one(p) for p in re.split(r"\s*/\s*|\s*\u060c\s*|\s+[\-\u2013\u2014]\s+", s2) if clean_one(p)]
    if len(parts) > 1:
        shown = ["\u0627\u0633\u062a\u0627\u062f " + p for p in parts[:2]]
        return (shown[0] + "\u060c " + shown[1] + " \u0648...") if len(parts) > 2 else " \u0648 ".join(shown)
    return "\u0627\u0633\u062a\u0627\u062f " + (parts[0] if parts else s)
