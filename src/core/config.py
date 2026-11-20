import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
    _local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    APP_DATA_ROOT = Path(_local) / "eHadiPanel"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    APP_DATA_ROOT = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")
if (APP_DATA_ROOT / ".env").exists():
    load_dotenv(APP_DATA_ROOT / ".env", override=True)

class Config:
    APP_NAME: str = "پنل مدیریت مؤسسه امام هادی"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    DATA_DIR: Path = APP_DATA_ROOT
    RAW_DOCS_DIR: Path = DATA_DIR / "raw_docs"
    STORAGE_DIR: Path = DATA_DIR / "storage"
    BACKUPS_DIR: Path = DATA_DIR / "backups"
    LOGS_DIR: Path = DATA_DIR / "logs"

    LANCEDB_PATH: Path = STORAGE_DIR / "lancedb"
    DUCKDB_PATH: Path = STORAGE_DIR / "ehadi.duckdb"

    @classmethod
    def ensure_directories(cls) -> None:
        for d in (cls.RAW_DOCS_DIR, cls.STORAGE_DIR, cls.LANCEDB_PATH, cls.BACKUPS_DIR, cls.LOGS_DIR):
            d.mkdir(parents=True, exist_ok=True)

Config.ensure_directories()
