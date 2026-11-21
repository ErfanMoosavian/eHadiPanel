from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Callable

logger = logging.getLogger("eHadiPanel.SmartBrain")

FA_DIGITS = "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"
AR_DIGITS = "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
ZWNJ = "\u200c"

_FORBIDDEN_SQL_RX = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|REPLACE|ATTACH|DETACH|COPY|EXPORT|IMPORT|LOAD|INSTALL|CALL|PRAGMA\s+database_size)\b",
    re.IGNORECASE,
)
_ALLOWED_START_RX = re.compile(
    r"^\s*(SELECT|WITH|DESCRIBE|SHOW|SUMMARIZE|VALUES)\b",
    re.IGNORECASE,
)


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def normalize_persian_text(text: Any) -> str:
    if text is None:
        return ""
    s = re.sub(r"[\u064b-\u065f\u0670\u0640]+", "", str(text))
    trans = str.maketrans(
        FA_DIGITS + AR_DIGITS + "\u064a\u0643\u0623\u0625\u0629" + ZWNJ,
        "01234567890123456789\u06cc\u06a9\u0627\u0627\u0647 ",
    )
    s = s.translate(trans)
    return re.sub(r"\s+", " ", s).strip()


def parse_dirty_number(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = normalize_persian_text(val)
    if not s:
        return None
    # Reject dates like 1404/08/29 or 2026-11-20
    if re.search(r"\d{2,4}[/\-]\d{1,2}[/\-]\d{1,4}", s):
        return None
    s = s.replace("\u066b", ".").replace("\u066c", "").replace(",", "").replace("\u060c", "")
    cleaned = re.sub(r"[^0-9.\-]", "", s)
    if not cleaned or cleaned in {".", "-", "-."}:
        return None
    if cleaned.count(".") > 1 or cleaned.count("-") > 1:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def discover_duckdb_files(base_dir: Path | None = None) -> list[Path]:
    root = base_dir or _project_root()
    found: list[Path] = []
    seen: set[str] = set()
    folders: list[Path] = []
    if base_dir is None:
        try:
            from src.core.config import Config
            if getattr(Config, "DUCKDB_PATH", None) and Path(Config.DUCKDB_PATH).exists():
                p_main = Path(Config.DUCKDB_PATH).resolve()
                seen.add(str(p_main).lower())
                found.append(p_main)
            if getattr(Config, "STORAGE_DIR", None):
                folders.append(Path(Config.STORAGE_DIR))
        except Exception:
            pass
    folders.extend([root / "data", root])
    for folder in folders:
        if not folder.exists():
            continue
        for pat in ("*.duckdb", "*/*.duckdb"):
            for fp in sorted(folder.glob(pat)):
                key = str(fp.resolve()).lower()
                if key not in seen and fp.is_file():
                    seen.add(key)
                    found.append(fp)
    return found


def register_persian_macros(con) -> bool:
    """Registers fa_num(v) and fa_norm(v) DuckDB TEMP macros for dirty Persian data."""
    try:
        from_num = FA_DIGITS + AR_DIGITS + "\u066b"
        to_num = "01234567890123456789."
        con.execute(
            f"""
            CREATE OR REPLACE TEMP MACRO fa_num(v) AS (
                TRY_CAST(
                    NULLIF(
                        REGEXP_REPLACE(
                            TRANSLATE(CAST(v AS VARCHAR), '{from_num}', '{to_num}'),
                            '[^0-9.\\-]',
                            '',
                            'g'
                        ),
                        ''
                    ) AS DOUBLE
                )
            )
            """
        )
        from_txt = "\u064a\u0643\u0623\u0625\u0629" + ZWNJ
        diacritics = "[\u064b-\u065f\u0670\u0640]"
        to_txt = "\u06cc\u06a9\u0627\u0627\u0647 "
        con.execute(
            f"""
            CREATE OR REPLACE TEMP MACRO fa_norm(v) AS (
                TRIM(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            TRANSLATE(CAST(v AS VARCHAR), '{from_txt}', '{to_txt}'),
                            '{diacritics}', '', 'g'
                        ),
                        '\\s+',
                        ' ',
                        'g'
                    )
                )
            )
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP MACRO fa_mobile(v) AS (
                CASE
                    WHEN LENGTH(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                TRANSLATE(CAST(v AS VARCHAR), '{FA_DIGITS + AR_DIGITS}', '01234567890123456789'),
                                '\\.0+$', '', 'g'
                            ),
                            '[^0-9]', '', 'g'
                        )
                    ) >= 10
                    THEN RIGHT(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                TRANSLATE(CAST(v AS VARCHAR), '{FA_DIGITS + AR_DIGITS}', '01234567890123456789'),
                                '\\.0+$', '', 'g'
                            ),
                            '[^0-9]', '', 'g'
                        ),
                        10
                    )
                    ELSE NULL
                END
            )
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP MACRO fa_nid(v) AS (
                CASE
                    WHEN LENGTH(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                TRANSLATE(CAST(v AS VARCHAR), '{FA_DIGITS + AR_DIGITS}', '01234567890123456789'),
                                '\\.0+$', '', 'g'
                            ),
                            '[^0-9]', '', 'g'
                        )
                    ) BETWEEN 8 AND 10
                    THEN LPAD(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                TRANSLATE(CAST(v AS VARCHAR), '{FA_DIGITS + AR_DIGITS}', '01234567890123456789'),
                                '\\.0+$', '', 'g'
                            ),
                            '[^0-9]', '', 'g'
                        ),
                        10,
                        '0'
                    )
                    ELSE NULL
                END
            )
            """
        )
        return True
    except Exception as exc:
        logger.warning("Could not register Persian DuckDB macros: %s", exc)
        return False


def _infer_table_domain(table_name: str, col_names: list[str]) -> str:
    joined = normalize_persian_text(table_name + " " + " ".join(col_names)).lower()
    if any(k in joined for k in ("فاکتور", "مبلغ", "تومان", "ریال", "هزینه", "قیمت", "خرید", "مالی", "invoice", "amount", "price")):
        return "financial_invoices"
    if any(k in joined for k in ("دوره", "استاد", "کارگروه", "شرکت کننده", "شرکت‌کننده", "مخاطب", "سخنران", "کلاس", "course", "teacher")):
        return "educational_courses"
    if any(k in joined for k in ("کد ملی", "موبایل", "شماره تماس", "تلفن", "نام و نام خانوادگی", "پرسنل", "اعضا", "mobile", "national")):
        return "participants_roster"
    return "general_data"


def _detect_currency_hint(col_names: list[str], sample_texts: list[str]) -> str:
    blob = normalize_persian_text(" ".join(col_names) + " " + " ".join(sample_texts))
    has_toman = "تومان" in blob
    has_rial = "ریال" in blob
    if has_toman and has_rial:
        return "مختلط (تومان و ریال — نیاز به تفکیک)"
    if has_toman:
        return "تومان"
    if has_rial:
        return "ریال"
    return ""


class SemanticSchemaEngine:
    """
    Live Semantic Schema profiler with mtime-based caching and query-time relevance ranking
    so the AI assistant scales cleanly to dozens/hundreds of messy tables.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._explicit_db = Path(db_path) if db_path else None
        self._cache_sig: tuple | None = None
        self._cached_profiles: list[dict[str, Any]] = []

    def get_db_path(self) -> Path | None:
        if self._explicit_db and self._explicit_db.exists():
            return self._explicit_db
        dbs = discover_duckdb_files()
        return dbs[0] if dbs else None

    def get_profiles(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        db_path = self.get_db_path()
        if not db_path or not db_path.exists():
            return []
        st = db_path.stat()
        sig = (str(db_path.resolve()), st.st_mtime_ns, st.st_size)
        if not force_refresh and self._cache_sig == sig and self._cached_profiles:
            return self._cached_profiles

        import duckdb  # type: ignore
        from src.core.db_manager import get_db_lock

        _lk = get_db_lock(db_path)
        _lk.acquire()
        profiles: list[dict[str, Any]] = []
        con = None
        try:
            try:
                con = duckdb.connect(str(db_path))
            except Exception:
                con = duckdb.connect(str(db_path), read_only=True)

            from src.core.db_manager import INTERNAL_TABLES as _CORE_INTERNAL
            INTERNAL_TABLES = set(_CORE_INTERNAL)
            catalog_map: dict[str, dict[str, str]] = {}
            tables = [str(r[0]) for r in con.execute("SHOW TABLES").fetchall()]
            if "tabular_catalog" in tables:
                try:
                    cat_rows = con.execute(
                        "SELECT table_name, file_name, source_sheet FROM tabular_catalog"
                    ).fetchall()
                    for r in cat_rows:
                        catalog_map[str(r[0])] = {
                            "file_name": str(r[1] or ""),
                            "source_sheet": str(r[2] or ""),
                        }
                except Exception as cat_exc:
                    logger.warning("Could not read tabular_catalog: %s", cat_exc)

            for tname in tables:
                if tname.lower() in INTERNAL_TABLES:
                    continue
                safe_t = tname.replace('"', '""')
                try:
                    row_count = int(con.execute(f'SELECT COUNT(*) FROM "{safe_t}"').fetchone()[0])
                    desc = con.execute(f'DESCRIBE "{safe_t}"').fetchall()
                    col_names = [str(c[0]) for c in desc]
                    col_types = {str(c[0]): str(c[1]) for c in desc}

                    sample_rows = con.execute(f'SELECT * FROM "{safe_t}" LIMIT 50').fetchall()
                    sample_texts: list[str] = []
                    col_profiles: list[dict[str, Any]] = []

                    for ci, cname in enumerate(col_names):
                        vals = [r[ci] for r in sample_rows if ci < len(r) and r[ci] is not None and str(r[ci]).strip() != ""]
                        distinct_preview: list[str] = []
                        seen_v: set[str] = set()
                        parsed_nums: list[float] = []

                        for v in vals:
                            sv = str(v).strip()
                            if len(sv) <= 60:
                                sample_texts.append(sv)
                            norm_sv = normalize_persian_text(sv)
                            if norm_sv and norm_sv not in seen_v and len(distinct_preview) < 4:
                                seen_v.add(norm_sv)
                                distinct_preview.append(sv[:45])
                            pn = parse_dirty_number(v)
                            if pn is not None:
                                parsed_nums.append(pn)

                        ctype = col_types[cname]
                        is_native_num = any(k in ctype.upper() for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BIGINT", "REAL"))
                        is_dirty_num = (not is_native_num) and len(vals) >= 2 and (len(parsed_nums) / max(1, len(vals)) >= 0.7)

                        c_info: dict[str, Any] = {
                            "name": cname,
                            "type": ctype,
                            "dirty_numeric": is_dirty_num,
                            "samples": distinct_preview,
                        }
                        if (is_native_num or is_dirty_num) and parsed_nums:
                            c_info["sample_min"] = min(parsed_nums)
                            c_info["sample_max"] = max(parsed_nums)
                        col_profiles.append(c_info)

                    domain = _infer_table_domain(tname, col_names)
                    currency = _detect_currency_hint(col_names, sample_texts) if domain == "financial_invoices" else ""

                    cat_meta = catalog_map.get(tname, {})
                    src_file = cat_meta.get("file_name", "")
                    src_sheet = cat_meta.get("source_sheet", "")
                    profiles.append(
                        {
                            "table": tname,
                            "file_name": src_file,
                            "source_sheet": src_sheet,
                            "rows": row_count,
                            "domain": domain,
                            "currency_hint": currency,
                            "columns": col_profiles,
                            "search_blob": normalize_persian_text(
                                f"{tname} {src_file} {src_sheet} {domain} " + " ".join(col_names) + " " + " ".join(sample_texts[:25])
                            ).lower(),
                        }
                    )
                except Exception as t_exc:
                    logger.warning("Skipping table %s during profiling: %s", tname, t_exc)

            self._cache_sig = sig
            self._cached_profiles = profiles
            return profiles
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
            try:
                _lk.release()
            except Exception:
                pass

    def build_prompt_context(self, question: str = "", max_detailed_tables: int = 12) -> str:
        profiles = self.get_profiles()
        if not profiles:
            return "هیچ جدولی در پایگاه‌داده DuckDB یافت نشد."

        q_norm = normalize_persian_text(question).lower()
        q_tokens = [tok for tok in re.split(r"[\s،,.;:؟?!()\"']+", q_norm) if len(tok) >= 2]

        scored: list[tuple[int, dict[str, Any]]] = []
        fin_q = any(k in q_norm for k in ("فاکتور", "مبلغ", "تومان", "ریال", "هزینه", "خرید", "مالی", "بودجه"))
        edu_q = any(k in q_norm for k in ("دوره", "استاد", "کارگروه", "شرکت", "مخاطب", "سخنران", "کلاس"))
        prs_q = any(k in q_norm for k in ("کد ملی", "موبایل", "تماس", "پرسنل", "اعضا", "مخاطبان"))

        for p in profiles:
            score = 0
            if p["rows"] > 0:
                score += 2
            dom = p.get("domain", "general_data")
            if fin_q and dom == "financial_invoices":
                score += 12
            if edu_q and dom == "educational_courses":
                score += 12
            if prs_q and dom == "participants_roster":
                score += 12
            blob = p["search_blob"]
            for tok in q_tokens:
                if tok in blob:
                    score += 5
                if tok in normalize_persian_text(p["table"]).lower():
                    score += 8
            scored.append((score, p))

        scored.sort(key=lambda x: (x[0], x[1]["rows"]), reverse=True)
        detailed = [p for _, p in scored[:max_detailed_tables]]
        rest = [p for _, p in scored[max_detailed_tables:]]

        lines = [f"### نقشه معنایی زنده جداول DuckDB (تعداد کل جداول: {len(profiles)})"]
        for p in detailed:
            cur_note = f" | واحد مالی: {p['currency_hint']}" if p["currency_hint"] else ""
            src_lbl = " — ".join(x for x in (p.get("file_name", ""), p.get("source_sheet", "")) if x)
            src_note = f" | منبع: {src_lbl}" if src_lbl else ""
            lines.append(f'- جدول `"{p["table"]}"` ({p["rows"]} ردیف | حوزه: {p["domain"]}{src_note}{cur_note}):')
            for c in p["columns"]:
                dirty_tag = " [متنِ عددی: با fa_num() تبدیل شود]" if c["dirty_numeric"] else ""
                samp = "، ".join(c["samples"]) if c["samples"] else "-"
                lines.append(f'    * `"{c["name"]}"` ({c["type"]}{dirty_tag}) | نمونه: {samp}')

        if rest:
            summary_list = ", ".join(f'"{p["table"]}" ({p["rows"]})' for p in rest[:30])
            lines.append(f"\nسایر جداول موجود: {summary_list}")

        return "\n".join(lines)


@dataclass
class QueryExecutionResult:
    ok: bool
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    deterministic_stats: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: int = 1
    repair_history: list[str] = field(default_factory=list)

    def to_markdown_table(self, max_rows: int = 40) -> str:
        if not self.columns or not self.rows:
            return "(نتیجه‌ای یافت نشد)"
        shown = self.rows[:max_rows]
        header = "| " + " | ".join(str(c) for c in self.columns) + " |"
        sep = "| " + " | ".join("---" for _ in self.columns) + " |"
        body = [
            "| " + " | ".join(str("" if v is None else v).replace("|", "¦").replace("\n", " ") for v in r) + " |"
            for r in shown
        ]
        out = "\n".join([header, sep] + body)
        if len(self.rows) > max_rows:
            out += f"\n\n*(نمایش {max_rows} ردیف اول از {self.row_count} ردیف)*"
        return out


class SafeDuckDBExecutor:
    """Read-only validated DuckDB query runner with Persian macros & deterministic stats."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._explicit_db = Path(db_path) if db_path else None

    @staticmethod
    def validate_readonly_sql(sql: str) -> tuple[bool, str]:
        if not sql or not sql.strip():
            return False, "کوئری SQL خالی است."
        cleaned = re.sub(r"--[^\n]*", " ", sql)
        cleaned = re.sub(r"/\*[\s\S]*?\*/", " ", cleaned).strip()
        cleaned_no_trail = cleaned.rstrip(";").strip()
        if ";" in cleaned_no_trail:
            return False, "اجرای چند دستور هم‌زمان مجاز نیست."
        if not _ALLOWED_START_RX.match(cleaned_no_trail):
            return False, "فقط دستورات خواندنی (SELECT / WITH / DESCRIBE / SHOW) مجاز هستند."
        # Strip single-quoted string literals before checking forbidden DDL/DML words
        no_strings = re.sub(r"'(?:''|[^'])*'", "''", cleaned_no_trail)
        m = _FORBIDDEN_SQL_RX.search(no_strings)
        if m:
            return False, f"دستور غیرمجاز در حالت خواندنی: {m.group(1)}"
        return True, cleaned_no_trail

    @staticmethod
    def compute_deterministic_stats(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
        stats: dict[str, Any] = {"returned_rows": len(rows), "numeric_columns": {}}
        if not columns or not rows:
            return stats
        for ci, cname in enumerate(columns):
            nums: list[float] = []
            for r in rows:
                if ci < len(r):
                    v = parse_dirty_number(r[ci])
                    if v is not None:
                        nums.append(v)
            if len(nums) >= max(1, int(len(rows) * 0.6)):
                total = sum(nums)
                s_nums = sorted(nums)
                mid = len(s_nums) // 2
                med = (s_nums[mid] if len(s_nums) % 2 == 1 else (s_nums[mid - 1] + s_nums[mid]) / 2.0)
                stats["numeric_columns"][cname] = {
                    "count": len(nums),
                    "sum": round(total, 2),
                    "avg": round(total / len(nums), 2),
                    "median": round(med, 2),
                    "min": round(s_nums[0], 2),
                    "max": round(s_nums[-1], 2),
                }
        return stats

    def execute(self, sql: str, max_rows: int = 250) -> QueryExecutionResult:
        ok_sql, clean_or_err = self.validate_readonly_sql(sql)
        if not ok_sql:
            return QueryExecutionResult(ok=False, sql=sql, error=clean_or_err)

        db_path = self._explicit_db if (self._explicit_db and self._explicit_db.exists()) else None
        if db_path is None:
            dbs = discover_duckdb_files()
            db_path = dbs[0] if dbs else None
        if not db_path:
            return QueryExecutionResult(ok=False, sql=clean_or_err, error="فایل پایگاه‌داده DuckDB یافت نشد.")

        import duckdb  # type: ignore
        from src.core.db_manager import get_db_lock

        _lk = get_db_lock(db_path)
        _lk.acquire()
        con = None
        try:
            try:
                con = duckdb.connect(str(db_path))
            except Exception:
                con = duckdb.connect(str(db_path), read_only=True)

            register_persian_macros(con)
            cur = con.execute(clean_or_err)
            cols = [d[0] for d in (cur.description or [])]
            fetched = cur.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            rows = [list(r) for r in fetched[:max_rows]]
            det_stats = self.compute_deterministic_stats(cols, rows)

            return QueryExecutionResult(
                ok=True,
                sql=clean_or_err,
                columns=cols,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                deterministic_stats=det_stats,
            )
        except Exception as exc:
            return QueryExecutionResult(ok=False, sql=clean_or_err, error=str(exc))
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
            try:
                _lk.release()
            except Exception:
                pass


def _extract_sql_from_llm(raw_text: str) -> tuple[str, bool]:
    txt = (raw_text or "").strip()
    if not txt:
        return "", False
    # 1. Try JSON payload
    m_json = re.search(r"\{[\s\S]*\}", txt)
    if m_json:
        try:
            obj = json.loads(m_json.group(0))
            if isinstance(obj, dict):
                needs = bool(obj.get("needs_sql", True))
                sql = str(obj.get("sql") or "").strip()
                if sql:
                    return sql, needs
                if not needs:
                    return "", False
        except Exception:
            pass
    # 2. Try ```sql ... ``` fence
    m_fence = re.search(r"```(?:sql)?\s*([\s\S]*?)```", txt, re.IGNORECASE)
    if m_fence:
        return m_fence.group(1).strip(), True
    # 3. Direct SELECT / WITH
    if _ALLOWED_START_RX.match(txt):
        return txt, True
    return "", False


class SelfHealingSQLAgent:
    """
    Up-to-3-attempt Self-Correcting SQL Brain:
    LLM translates question -> DuckDB executes deterministically ->
    on SQL error or strict-match 0-row Persian filter, automatically repairs & retries.
    """

    def __init__(self, db_path: Path | str | None = None, max_retries: int = 3) -> None:
        self.schema_engine = SemanticSchemaEngine(db_path)
        self.executor = SafeDuckDBExecutor(db_path)
        self.max_retries = max(1, min(4, int(max_retries)))

    def run(
        self,
        question: str,
        llm_call: Callable[[str, str], str],
        extra_rules: str = "",
    ) -> QueryExecutionResult:
        schema_ctx = self.schema_engine.build_prompt_context(question=question)
        sys_prompt = (
            "تو یک مهندس ارشد DuckDB برای سامانه فارسی مؤسسه امام هادی هستی.\n"
            "قوانین حیاتی نوشتن کوئری:\n"
            "1. نام تمام جداول و ستون‌های فارسی را حتماً داخل دبل‌کوتیشن \"...\" بگذار.\n"
            "2. برای فیلتر کردن متن‌های فارسی (نام استاد، نام دوره، کارگروه)، حتماً از ماکروی fa_norm(\"ستون\") LIKE '%' || fa_norm('عبارت') || '%' استفاده کن.\n"
            "3. برای جمع یا میانگین ستون‌هایی که نوع متنی دارند یا برچسب [متنِ عددی] دارند، حتماً از fa_num(\"ستون\") استفاده کن.\n"
            "4. فقط کوئری SELECT/WITH بنویس و هرگز نام ستون یا جدول را حدس نزن.\n"
            "5. خروجی را صرفاً به‌صورت JSON معتبر برگردان: {\"needs_sql\": true, \"sql\": \"SELECT ...\"}\n"
            "اگر سؤال اصلاً نیازی به دیتابیس نداشت، برگردان: {\"needs_sql\": false, \"sql\": \"\"}\n"
        )
        if extra_rules:
            sys_prompt += "\nقوانین دائمی کاربر:\n" + extra_rules.strip() + "\n"

        user_prompt = f"{schema_ctx}\n\nسؤال کاربر:\n{question}"
        repair_history: list[str] = []
        last_res = QueryExecutionResult(ok=False, sql="", error="کوئری تولید نشد.")

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_llm = llm_call(sys_prompt, user_prompt)
            except Exception as llm_exc:
                return QueryExecutionResult(
                    ok=False,
                    sql="",
                    error=f"خطا در ارتباط با مدل هوشمند: {llm_exc}",
                    attempts=attempt,
                    repair_history=repair_history,
                )

            sql, needs_sql = _extract_sql_from_llm(raw_llm)
            if not needs_sql:
                return QueryExecutionResult(ok=True, sql="", attempts=attempt, repair_history=repair_history)

            res = self.executor.execute(sql)
            res.attempts = attempt
            res.repair_history = list(repair_history)
            last_res = res

            if res.ok:
                # Smart zero-row self-healing: if WHERE used strict '=' without fa_norm/LIKE, retry once with fuzzy Persian match
                if res.row_count == 0 and attempt < self.max_retries and "WHERE" in res.sql.upper() and "FA_NORM" not in res.sql.upper():
                    note = f"تلاش {attempt}: نتیجه صفر ردیف بود؛ اصلاح فیلتر با fa_norm() و LIKE."
                    repair_history.append(note)
                    user_prompt = (
                        f"{schema_ctx}\n\nسؤال کاربر: {question}\n\n"
                        f"کوئری قبلی هیچ ردیفی برنگرداند:\n```sql\n{res.sql}\n```\n"
                        "احتمالاً به دلیل تفاوت حروف فارسی (ی/ک/نیم‌فاصله) یا تطابق دقیق (=) بوده است. "
                        "کوئری را با استفاده از fa_norm(\"ستون\") LIKE '%' || fa_norm('...') || '%' اصلاح کن و فقط JSON برگردان."
                    )
                    continue
                res.repair_history = list(repair_history)
                return res

            # Execution failed -> feed exact DuckDB error back to LLM to self-heal
            repair_history.append(f"تلاش {attempt} خطا داد: {res.error[:240]}")
            logger.warning("SmartBrain SQL attempt %d failed: %s", attempt, res.error)
            user_prompt = (
                f"{schema_ctx}\n\nسؤال کاربر: {question}\n\n"
                f"کوئری قبلی تو با این خطای DuckDB مواجه شد:\n{res.error}\n\n"
                f"کوئری خطادار:\n```sql\n{sql}\n```\n"
                "لطفاً دقیقاً بر اساس نام واقعی جداول و ستون‌های بالا کوئری را اصلاح کن "
                "(از دبل‌کوتیشن برای نام ستون‌ها و از fa_num / fa_norm در صورت نیاز استفاده کن) و فقط JSON برگردان."
            )

        last_res.repair_history = repair_history
        return last_res
