import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pymupdf
import lancedb
import pandas as pd
from docx import Document as DocxDocument
from pptx import Presentation

from src.core.config import Config
from src.core.db_manager import format_jalali_now, get_db_lock

try:
    import pyodbc
except ImportError:
    pyodbc = None


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".accdb", ".mdb"}


class DocumentIngestionEngine:
    """موتور استخراج متن و جداول از اسناد و ذخیره‌سازی در DuckDB و LanceDB"""

    def __init__(self):
        Config.ensure_directories()
        self.duckdb_path = str(Config.DUCKDB_PATH)
        self.lancedb_path = str(Config.LANCEDB_PATH)
        self._init_duckdb()

    def _connect_duckdb(self):
        return duckdb.connect(self.duckdb_path)

    def _init_duckdb(self) -> None:
        with get_db_lock(self.duckdb_path):
            self._init_duckdb_locked()

    def _init_duckdb_locked(self) -> None:
        con = self._connect_duckdb()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_name VARCHAR,
                    file_path VARCHAR PRIMARY KEY,
                    file_type VARCHAR,
                    file_hash VARCHAR,
                    chunks_count INTEGER,
                    tables_count INTEGER,
                    rows_count INTEGER,
                    status VARCHAR,
                    message VARCHAR,
                    processed_at VARCHAR
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS tabular_catalog (
                    table_name VARCHAR PRIMARY KEY,
                    file_name VARCHAR,
                    source_sheet VARCHAR,
                    rows_count INTEGER,
                    columns_json VARCHAR
                )
            """)
        finally:
            con.close()

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        if not cleaned:
            return []
        if len(cleaned) <= chunk_size:
            return [cleaned]

        chunks = []
        start = 0
        while start < len(cleaned):
            end = start + chunk_size
            chunks.append(cleaned[start:end].strip())
            if end >= len(cleaned):
                break
            start = max(end - overlap, start + 1)
        return chunks

    @staticmethod
    def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna(how="all").dropna(axis=1, how="all").copy()
        new_cols = []
        seen: dict[str, int] = {}
        for idx, col in enumerate(df.columns):
            name = str(col).strip()
            if not name or name.lower().startswith("unnamed:"):
                name = f"ستون_{idx + 1}"
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 1
            new_cols.append(name)
        df.columns = new_cols
        return df

    def _save_dataframe_to_duckdb(
        self, con: duckdb.DuckDBPyConnection, df: pd.DataFrame, file_name: str, sheet_name: str
    ) -> tuple[str, int, list[str]]:
        df = self._clean_dataframe(df)
        if df.empty:
            return "", 0, []

        raw_key = f"{file_name}__{sheet_name}".encode("utf-8")
        table_name = f"tbl_{hashlib.md5(raw_key).hexdigest()[:10]}"

        try:
            con.register("temp_ingest_df", df)
            con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM temp_ingest_df')
            con.unregister("temp_ingest_df")
        except Exception:
            safe_df = df.fillna("").astype(str)
            con.register("temp_ingest_df", safe_df)
            con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM temp_ingest_df')
            con.unregister("temp_ingest_df")

        cols = list(df.columns)
        con.execute("DELETE FROM tabular_catalog WHERE table_name = ?", [table_name])
        con.execute(
            "INSERT INTO tabular_catalog VALUES (?, ?, ?, ?, ?)",
            [table_name, file_name, sheet_name, int(len(df)), json.dumps(cols, ensure_ascii=False)],
        )
        return table_name, int(len(df)), cols

    @classmethod
    def _iter_shapes(cls, shapes):
        for shape in shapes:
            if hasattr(shape, "shapes"):
                yield from cls._iter_shapes(shape.shapes)
            else:
                yield shape

    def _parse_pdf(self, path: Path) -> list[dict[str, Any]]:
        chunks = []
        with pymupdf.open(path) as doc:
            for page_idx, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                for part_idx, part in enumerate(self._chunk_text(text), start=1):
                    chunks.append({
                        "chunk_id": f"{path.name}_p{page_idx}_{part_idx}",
                        "file_name": path.name,
                        "file_path": str(path),
                        "file_type": "PDF",
                        "location": f"صفحه {page_idx}",
                        "content": part,
                    })
        return chunks

    def _parse_docx(self, path: Path) -> list[dict[str, Any]]:
        doc = DocxDocument(path)
        blocks = []
        for p in doc.paragraphs:
            if p.text.strip():
                blocks.append(p.text.strip())

        for t_idx, table in enumerate(doc.tables, start=1):
            rows_text = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    rows_text.append(" | ".join(cells))
            if rows_text:
                blocks.append(f"[جدول {t_idx}]\n" + "\n".join(rows_text))

        full_text = "\n".join(blocks)
        chunks = []
        for idx, part in enumerate(self._chunk_text(full_text), start=1):
            chunks.append({
                "chunk_id": f"{path.name}_s{idx}",
                "file_name": path.name,
                "file_path": str(path),
                "file_type": "DOCX",
                "location": f"بخش {idx}",
                "content": part,
            })
        return chunks

    def _parse_pptx(
        self, path: Path, con: duckdb.DuckDBPyConnection
    ) -> tuple[list[dict[str, Any]], int, int]:
        prs = Presentation(path)
        chunks = []
        tables_count = 0
        total_rows = 0

        for slide_idx, slide in enumerate(prs.slides, start=1):
            texts = []
            slide_table_idx = 0

            for shape in self._iter_shapes(slide.shapes):
                if getattr(shape, "has_text_frame", False):
                    t = shape.text_frame.text.strip()
                    if t:
                        texts.append(t)
                if getattr(shape, "has_table", False):
                    slide_table_idx += 1
                    raw_rows = []
                    for row in shape.table.rows:
                        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                        if any(cells):
                            raw_rows.append(cells)
                            texts.append(" | ".join(cells))

                    if len(raw_rows) >= 2:
                        header = raw_rows[0]
                        body = raw_rows[1:]
                        df = pd.DataFrame(body, columns=header)
                        sheet_label = f"اسلاید {slide_idx} (جدول {slide_table_idx})"
                        tbl_name, r_cnt, _ = self._save_dataframe_to_duckdb(
                            con, df, path.name, sheet_label
                        )
                        if tbl_name:
                            tables_count += 1
                            total_rows += r_cnt

            slide_text = "\n".join(texts)
            for part_idx, part in enumerate(self._chunk_text(slide_text), start=1):
                chunks.append({
                    "chunk_id": f"{path.name}_sl{slide_idx}_{part_idx}",
                    "file_name": path.name,
                    "file_path": str(path),
                    "file_type": "PPTX",
                    "location": f"اسلاید {slide_idx}",
                    "content": part,
                })

        return chunks, tables_count, total_rows

    def _parse_excel(
        self, path: Path, con: duckdb.DuckDBPyConnection
    ) -> tuple[list[dict[str, Any]], int, int]:
        sheets = pd.read_excel(path, sheet_name=None)
        chunks = []
        tables_count = 0
        total_rows = 0

        for sheet_name, df in sheets.items():
            table_name, rows_count, cols = self._save_dataframe_to_duckdb(
                con, df, path.name, str(sheet_name)
            )
            if not table_name:
                continue
            tables_count += 1
            total_rows += rows_count
            preview_text = df.head(8).fillna("").to_string(index=False)
            summary = (
                f"فایل اکسل: {path.name} | شیت: {sheet_name} | نام جدول در دیتابیس: {table_name} | "
                f"تعداد ردیف: {rows_count} | ستون‌ها: {', '.join(cols)}\nنمونه داده‌ها:\n{preview_text}"
            )
            chunks.append({
                "chunk_id": f"{path.name}_{table_name}",
                "file_name": path.name,
                "file_path": str(path),
                "file_type": "EXCEL",
                "location": f"شیت «{sheet_name}»",
                "content": summary,
            })

        return chunks, tables_count, total_rows

    def _parse_access(
        self, path: Path, con: duckdb.DuckDBPyConnection
    ) -> tuple[list[dict[str, Any]], int, int]:
        if pyodbc is None:
            raise RuntimeError("کتابخانه pyodbc نصب نیست.")

        drivers = [d for d in pyodbc.drivers() if "Access Driver" in d]
        if not drivers:
            raise RuntimeError(
                "درایور Microsoft Access Database Engine (64-bit) روی ویندوز نصب نیست."
            )

        conn_str = f"DRIVER={{{drivers[0]}}};DBQ={path};"
        chunks = []
        tables_count = 0
        total_rows = 0

        access_con = pyodbc.connect(conn_str)
        try:
            cursor = access_con.cursor()
            table_names = [
                row.table_name
                for row in cursor.tables(tableType="TABLE")
                if not row.table_name.startswith("MSys")
            ]
            for acc_table in table_names:
                df = pd.read_sql(f"SELECT * FROM [{acc_table}]", access_con)
                table_name, rows_count, cols = self._save_dataframe_to_duckdb(
                    con, df, path.name, acc_table
                )
                if not table_name:
                    continue
                tables_count += 1
                total_rows += rows_count
                preview_text = df.head(8).fillna("").to_string(index=False)
                summary = (
                    f"دیتابیس اکسس: {path.name} | جدول: {acc_table} | نام جدول تحلیلی: {table_name} | "
                    f"تعداد رکورد: {rows_count} | ستون‌ها: {', '.join(cols)}\nنمونه رکوردها:\n{preview_text}"
                )
                chunks.append({
                    "chunk_id": f"{path.name}_{table_name}",
                    "file_name": path.name,
                    "file_path": str(path),
                    "file_type": "ACCESS",
                    "location": f"جدول «{acc_table}»",
                    "content": summary,
                })
        finally:
            access_con.close()

        return chunks, tables_count, total_rows

    def ingest_all(self) -> dict[str, Any]:
        """اسکن کامل پوشه raw_docs و به‌روزرسانی DuckDB و LanceDB"""
        raw_dir = Config.RAW_DOCS_DIR
        files = [
            p for p in raw_dir.rglob("*")
            if p.is_file()
            and not p.name.startswith("~$")
            and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        all_chunks: list[dict[str, Any]] = []
        warnings: list[str] = []
        _lk = get_db_lock(self.duckdb_path)
        _lk.acquire()
        con = self._connect_duckdb()

        db_lance = lancedb.connect(self.lancedb_path)
        has_lance_tbl = "document_chunks" in db_lance.table_names()
        existing_lance_rows: list[dict[str, Any]] = []
        if has_lance_tbl:
            try:
                existing_lance_rows = db_lance.open_table("document_chunks").to_pandas().to_dict(orient="records")
            except Exception:
                existing_lance_rows = []

        try:
            prev_files_rows = con.execute(
                "SELECT file_path, file_name, file_type, file_hash, chunks_count, tables_count, rows_count, status, message, processed_at "
                "FROM processed_files WHERE status = 'موفق'"
            ).fetchall()
            prev_by_path = {str(r[0]): r for r in prev_files_rows}
            current_paths = {str(p) for p in files}

            # Remove deleted files' tables & catalog entries (including any previous failed entries)
            all_prev_paths = {str(r[0]) for r in con.execute("SELECT file_path FROM processed_files").fetchall()}
            removed_paths = all_prev_paths - current_paths
            if removed_paths:
                rem_names = {prev_by_path[rp][1] for rp in removed_paths if rp in prev_by_path}
                if rem_names:
                    ph = ",".join("?" for _ in rem_names)
                    rem_tbls = con.execute(f"SELECT table_name FROM tabular_catalog WHERE file_name IN ({ph})", list(rem_names)).fetchall()
                    for (rt,) in rem_tbls:
                        con.execute(f'DROP TABLE IF EXISTS "{rt}"')
                    con.execute(f"DELETE FROM tabular_catalog WHERE file_name IN ({ph})", list(rem_names))
                con.execute(
                    f"DELETE FROM processed_files WHERE file_path IN ({','.join('?' for _ in removed_paths)})",
                    list(removed_paths),
                )
                existing_lance_rows = [row for row in existing_lance_rows if row.get("file_name") not in rem_names]

            # Keep unchanged files intact when LanceDB chunks exist
            unchanged_paths: set[str] = set()
            if has_lance_tbl:
                for p in files:
                    sp = str(p)
                    pr = prev_by_path.get(sp)
                    if pr and pr[3] == self._file_hash(p):
                        fn_match = pr[1]
                        f_chunks = [ch for ch in existing_lance_rows if ch.get("file_name") == fn_match]
                        if int(pr[4] or 0) == 0 or len(f_chunks) > 0:
                            unchanged_paths.add(sp)
                            all_chunks.extend(f_chunks)

            # Re-parse only changed or newly added files
            for p in files:
                sp = str(p)
                if sp in unchanged_paths:
                    continue
                pr = prev_by_path.get(sp)
                fn_old = pr[1] if pr else p.name
                old_t = con.execute("SELECT table_name FROM tabular_catalog WHERE file_name = ?", [fn_old]).fetchall()
                for (ot,) in old_t:
                    con.execute(f'DROP TABLE IF EXISTS "{ot}"')
                con.execute("DELETE FROM tabular_catalog WHERE file_name = ?", [fn_old])
                con.execute("DELETE FROM processed_files WHERE file_path = ?", [sp])
                existing_lance_rows = [row for row in existing_lance_rows if row.get("file_name") != fn_old]

            now_str = format_jalali_now(include_time=True, fa_digits=True)

            for path in sorted(files, key=lambda x: x.name.lower()):
                if str(path) in unchanged_paths:
                    continue
                ext = path.suffix.lower()
                file_type = ext.lstrip(".").upper()
                f_hash = self._file_hash(path)
                chunks_count = 0
                tables_count = 0
                rows_count = 0
                status = "موفق"
                msg = "پردازش با موفقیت انجام شد"

                try:
                    if ext == ".pdf":
                        c = self._parse_pdf(path)
                        all_chunks.extend(c)
                        chunks_count = len(c)
                    elif ext == ".docx":
                        c = self._parse_docx(path)
                        all_chunks.extend(c)
                        chunks_count = len(c)
                    elif ext == ".pptx":
                        c, tables_count, rows_count = self._parse_pptx(path, con)
                        all_chunks.extend(c)
                        chunks_count = len(c)
                    elif ext in {".xlsx", ".xls"}:
                        c, tables_count, rows_count = self._parse_excel(path, con)
                        all_chunks.extend(c)
                        chunks_count = len(c)
                    elif ext in {".accdb", ".mdb"}:
                        c, tables_count, rows_count = self._parse_access(path, con)
                        all_chunks.extend(c)
                        chunks_count = len(c)
                except Exception as exc:
                    status = "خطا"
                    msg = str(exc)
                    warnings.append(f"{path.name}: {msg}")

                con.execute("DELETE FROM processed_files WHERE file_path = ?", [str(path)])
                con.execute(
                    "INSERT INTO processed_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        path.name,
                        str(path),
                        file_type,
                        f_hash,
                        chunks_count,
                        tables_count,
                        rows_count,
                        status,
                        msg,
                        now_str,
                    ],
                )
        finally:
            con.close()
            _lk.release()

        if all_chunks:
            db_lance.create_table("document_chunks", data=all_chunks, mode="overwrite")
        else:
            if "document_chunks" in db_lance.table_names():
                db_lance.drop_table("document_chunks")

        data = self.get_dashboard_stats()
        data["warnings"] = warnings
        return data

    def get_dashboard_stats(self) -> dict[str, Any]:
        with get_db_lock(self.duckdb_path):
            con = self._connect_duckdb()
            try:
                files_rows = con.execute("""
                    SELECT file_name, file_type, chunks_count, tables_count, rows_count, status, message, processed_at
                    FROM processed_files
                    ORDER BY processed_at DESC, file_name ASC
                """).fetchall()
                tables_count = con.execute("SELECT COUNT(*) FROM tabular_catalog").fetchone()[0]
                total_rows = con.execute("SELECT COALESCE(SUM(rows_count), 0) FROM tabular_catalog").fetchone()[0]
            finally:
                con.close()

        total_chunks = 0
        db = lancedb.connect(self.lancedb_path)
        if "document_chunks" in db.table_names():
            tbl = db.open_table("document_chunks")
            total_chunks = len(tbl)

        files_list = [
            {
                "file_name": r[0],
                "file_type": r[1],
                "chunks_count": r[2],
                "tables_count": r[3],
                "rows_count": r[4],
                "status": r[5],
                "message": r[6],
                "processed_at": r[7],
            }
            for r in files_rows
        ]

        return {
            "total_files": len(files_list),
            "success_files": sum(1 for f in files_list if f["status"] == "موفق"),
            "total_tables": int(tables_count),
            "total_rows": int(total_rows),
            "total_chunks": int(total_chunks),
            "raw_docs_dir": str(Config.RAW_DOCS_DIR),
            "files": files_list,
        }