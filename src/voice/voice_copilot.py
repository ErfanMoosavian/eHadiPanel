from __future__ import annotations

import asyncio
import base64
import collections
import io
import json
import logging
import os
from pathlib import Path
import queue
import re
import threading
import time
from typing import Any
import wave

import duckdb
from google import genai
from google.genai import types
import numpy as np
import sounddevice as sd

from src.analytics.executive_engine import ExecutiveAnalyticsEngine
from src.core.config import BASE_DIR, Config
from src.reports.report_studio import load_branding

logger = logging.getLogger("eHadiPanel.Voice")

_stop_event = threading.Event()
_whisper_cache: dict[str, Any] = {"size": None, "model": None}
_vocab_cache: dict[str, Any] = {"ts": 0.0, "text": ""}

VOICE_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
]


def stop_active_recording() -> dict[str, Any]:
    _stop_event.set()
    return {"ok": True}


def _collect_api_keys() -> list[str]:
    keys: list[str] = []

    # 1. Primary source: Config.GEMINI_API_KEY (same key used by InstitutionalAIAgent)
    cfg_key = (getattr(Config, "GEMINI_API_KEY", "") or "").strip()
    if cfg_key and cfg_key != "کلید_API_خود_را_اینجا_بگذارید":
        keys.append(cfg_key)

    # 2. Environment variables
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "API_KEY"):
        v = (os.environ.get(name) or "").strip()
        if v and v not in keys:
            keys.append(v)

    # 3. Local config files fallback
    files = [
        Path(".env"),
        BASE_DIR / ".env",
        Config.STORAGE_DIR / ".env",
        Config.STORAGE_DIR / "settings.json",
        Config.STORAGE_DIR / "config.json",
        Config.DATA_DIR / "settings.json",
    ]
    for fp in files:
        if not fp or not fp.exists():
            continue
        raw = fp.read_text(encoding="utf-8", errors="ignore").strip()
        if fp.suffix.lower() == ".json":
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    for k in ("api_key", "gemini_api_key", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
                        val = str(obj.get(k) or "").strip()
                        if val and val not in keys:
                            keys.append(val)
            except Exception:
                pass
        else:
            for line in raw.splitlines():
                s = line.strip()
                if "=" in s and not s.startswith("#"):
                    k, v = s.split("=", 1)
                    if k.strip().upper() in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "API_KEY"):
                        val = v.strip().strip('"').strip("'")
                        if val and val not in keys:
                            keys.append(val)
    return keys


def _resample_to_16k(audio: np.ndarray, orig_sr: int) -> tuple[np.ndarray, int]:
    """Cleanly resamples any input sample rate (44100, 48000, 32000, etc.) to 16000 Hz mono float32."""
    target_sr = 16000
    if orig_sr == target_sr or len(audio) < 4:
        return audio.astype(np.float32), orig_sr
    if orig_sr == 48000 and len(audio) >= 3:
        n = (len(audio) // 3) * 3
        return audio[:n].reshape(-1, 3).mean(axis=1).astype(np.float32), target_sr
    ratio = target_sr / float(orig_sr)
    new_len = max(1, int(round(len(audio) * ratio)))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
    resampled = np.interp(x_new, x_old, audio).astype(np.float32)
    return resampled, target_sr


def _get_domain_vocab_hint() -> str:
    """Loads top institutional terms & teacher names (cached 5 min) to boost Persian STT accuracy."""
    now = time.time()
    if _vocab_cache["text"] and (now - _vocab_cache["ts"] < 300):
        return _vocab_cache["text"]

    base_terms = [
        "مؤسسه امام هادی", "کارگروه", "پرس‌لاین", "دبیرخانه", "ایتا",
        "هیئت‌مدیره", "گزارش ۵ ساله", "شرکت‌کنندگان", "دوره‌های کوتاه‌مدت",
    ]
    extra: list[str] = []
    try:
        db_p = Path(Config.DUCKDB_PATH)
        if db_p.exists():
            con = duckdb.connect(str(db_p), read_only=True)
            try:
                tbls = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
                if "smart_teachers_exploded" in tbls:
                    rows = con.execute(
                        'SELECT "نام_معیار_استاد", COUNT(*) AS c FROM smart_teachers_exploded '
                        'WHERE "نوع_برگزاری" != \'گروهی\' GROUP BY 1 ORDER BY c DESC LIMIT 20'
                    ).fetchall()
                    for r in rows:
                        name = str(r[0] or "").strip()
                        if name and len(name) <= 45:
                            extra.append(name)
            finally:
                con.close()
    except Exception:
        pass

    vocab = "، ".join(base_terms + extra[:18])
    _vocab_cache["ts"] = now
    _vocab_cache["text"] = vocab
    return vocab


def _record_wav_callback(max_seconds: float = 14.0, silence_seconds: float = 1.4) -> tuple[bool, bytes | str]:
    """ضبط بدون افت فریم با Callback، بافر پیش‌ضبط و تبدیل قطعی به 16kHz PCM16"""
    _stop_event.clear()
    try:
        dev_info = sd.query_devices(kind="input")
        sr = int(dev_info.get("default_samplerate") or 44100)
    except Exception:
        sr = 44100

    block_dur = 0.05
    block_size = max(256, int(sr * block_dur))
    q: queue.Queue[np.ndarray] = queue.Queue()

    def _cb(indata, frames, time_info, status):
        q.put(indata[:, 0].copy())

    pre_roll: collections.deque[np.ndarray] = collections.deque(maxlen=12)
    recorded: list[np.ndarray] = []
    speech_started = False
    silence_blocks = 0
    max_silence = int(silence_seconds / block_dur)
    max_blocks = int(max_seconds / block_dur)
    wait_limit = int(6.0 / block_dur)

    try:
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=block_size, callback=_cb):
            noise_vals = []
            for _ in range(7):
                blk = q.get(timeout=2.0)
                pre_roll.append(blk)
                noise_vals.append(float(np.sqrt(np.mean(np.square(blk)))))
            ambient = float(np.median(noise_vals)) if noise_vals else 0.004
            threshold = max(0.009, min(0.045, ambient * 2.1 + 0.004))

            for idx in range(max_blocks):
                if _stop_event.is_set():
                    break
                try:
                    blk = q.get(timeout=1.0)
                except queue.Empty:
                    break
                rms = float(np.sqrt(np.mean(np.square(blk))))
                if not speech_started:
                    pre_roll.append(blk)
                    if rms >= threshold:
                        speech_started = True
                        recorded.extend(pre_roll)
                        silence_blocks = 0
                    elif idx >= wait_limit:
                        break
                else:
                    recorded.append(blk)
                    if rms >= threshold:
                        silence_blocks = 0
                    else:
                        silence_blocks += 1
                        if silence_blocks >= max_silence:
                            break
    except Exception as exc:
        logger.exception("Microphone recording error")
        return False, f"خطای میکروفون ویندوز: {exc}"

    if not recorded or not speech_started:
        return False, "صدایی شنیده نشد؛ لطفاً نزدیک‌تر به میکروفون صحبت کنید."

    audio = np.concatenate(recorded, axis=0).astype(np.float32)
    audio, sr = _resample_to_16k(audio, sr)

    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 0.001:
        audio = np.clip(audio * (0.88 / peak), -1.0, 1.0)
    pcm16 = (audio * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    wav_bytes = buf.getvalue()

    try:
        (Config.STORAGE_DIR / "last_voice_test.wav").write_bytes(wav_bytes)
    except Exception:
        pass
    return True, wav_bytes


def _clean_whisper_loop(text: str) -> str:
    words = text.split()
    if not words:
        return ""
    cleaned: list[str] = []
    streak = 0
    for w in words:
        if cleaned and w == cleaned[-1]:
            streak += 1
            if streak >= 2:
                continue
        else:
            streak = 0
        cleaned.append(w)
    out = " ".join(cleaned).strip()
    m = re.match(r"^(.{3,35}?)(?:\s+\1){2,}", out)
    if m:
        out = m.group(1).strip()
    return out


def _whisper_transcribe(wav_bytes: bytes, model_size: str = "small") -> tuple[bool, str]:
    try:
        from faster_whisper import WhisperModel  # type: ignore

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            w_sr = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        audio, _ = _resample_to_16k(audio, w_sr)

        if len(audio) == 0 or float(np.sqrt(np.mean(np.square(audio)))) < 0.004:
            return False, "صدای واضحی شنیده نشد."

        model = _whisper_cache.get("model")
        if model is None or _whisper_cache.get("size") != model_size:
            last_err = ""
            for dev, ctype in (("cpu", "int8"), ("cpu", "float32")):
                try:
                    model = WhisperModel(model_size or "small", device=dev, compute_type=ctype)
                    _whisper_cache["model"] = model
                    _whisper_cache["size"] = model_size
                    break
                except Exception as exc:
                    last_err = str(exc)
            if model is None:
                return False, f"خطای بارگذاری ویسپر: {last_err}"

        segments, _ = model.transcribe(
            audio,
            language="fa",
            beam_size=3,
            temperature=0.0,
            repetition_penalty=1.2,
            no_repeat_ngram_size=2,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )
        parts: list[str] = []
        for seg in segments:
            if getattr(seg, "no_speech_prob", 0.0) > 0.72:
                continue
            t = (seg.text or "").strip()
            if t:
                parts.append(t)
        raw_text = _clean_whisper_loop(" ".join(parts).strip())
        return (True, raw_text) if raw_text else (False, "کلمه‌ای تشخیص داده نشد.")
    except Exception as exc:
        logger.exception("Whisper transcription error")
        return False, f"خطای ویسپر آفلاین: {exc}"


def _gemini_transcribe(wav_bytes: bytes) -> tuple[bool, str]:
    """Transcribes 16kHz Persian WAV via official google.genai SDK with institutional vocabulary hint."""
    keys = _collect_api_keys()
    if not keys:
        return False, "کلید Gemini API در تنظیمات ثبت نشده است."

    primary = (getattr(Config, "GEMINI_MODEL", "") or "").strip()
    models: list[str] = []
    if primary and "tts" not in primary.lower() and "image" not in primary.lower():
        models.append(primary)
    for m in VOICE_FALLBACK_MODELS:
        if m not in models:
            models.append(m)

    vocab = _get_domain_vocab_hint()
    prompt = (
        "متن گفته‌شده در این فایل صوتی فارسی را دقیقاً و کلمه‌به‌کلمه به فارسی روان بنویس. "
        "هیچ توضیح، پیشوند، یا ترجمه اضافه نکن. "
        f"واژگان و اسامی پرتکرار این سامانه برای دقت بیشتر املا: {vocab}"
    )

    audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
    last_err = ""

    for api_key in keys:
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=25000),
            )
        except Exception:
            client = genai.Client(api_key=api_key)

        for mdl in models:
            try:
                resp = client.models.generate_content(
                    model=mdl,
                    contents=[audio_part, prompt],
                    config=types.GenerateContentConfig(temperature=0.0),
                )
                txt = (getattr(resp, "text", None) or "").strip()
                if txt:
                    return True, txt
            except Exception as exc:
                last_err = str(exc)
                logger.warning("Gemini voice STT failed on %s: %s", mdl, last_err[:180])
                low = last_err.lower()
                if any(tok in low for tok in ("404", "not_found", "503", "429", "overloaded", "unavailable", "400")):
                    continue
                break

    return False, f"خطا در تشخیص گفتار جمینای: {last_err[:180]}"


def _answer_question_concisely(question: str) -> str:
    try:
        eng = ExecutiveAnalyticsEngine()
        courses, _, _ = eng._scan_duckdb()
        analytics = eng.get_executive_analytics({})
        k = analytics.get("kpis") or {}

        ordinals = {
            "اولین": 0, "دومین": 1, "سومین": 2, "چهارمین": 3, "پنجمین": 4,
            "ششمین": 5, "هفتمین": 6, "هشتمین": 7, "نهمین": 8, "دهمین": 9,
        }
        q_norm = question.replace("ي", "ی").replace("ك", "ک")
        if "دوره" in q_norm and courses:
            for word, idx in ordinals.items():
                if word in q_norm and idx < len(courses):
                    c = courses[idx]
                    t_part = f" با ارائه {c['teacher']}" if c.get("teacher") and c["teacher"] != "نامشخص" else ""
                    g_part = f" در کارگروه {c['group']}" if c.get("group") else ""
                    return f"{word} دوره ثبت‌شده، «{c['title']}»{t_part}{g_part} بوده است."

        if any(w in q_norm for w in ("چند دوره", "تعداد دوره", "چند تا دوره")):
            return f"در کل {k.get('total_courses', 0)} دوره با مجموع {k.get('total_attendance', 0)} نفر حضور ثبت شده است."
        if "یکتا" in q_norm:
            return f"تعداد شرکت‌کنندگان یکتای مؤسسه {k.get('unique_participants', 0)} نفر و نرخ بازگشت {k.get('repeat_rate', 0)} درصد است."
    except Exception:
        pass
    return "پرسش شما به دستیار هوشمند ارسال شد."


def _persian_tts_data_uri(text: str) -> str:
    if not text or not text.strip():
        return ""
    try:
        import edge_tts  # type: ignore

        async def _synth() -> bytes:
            comm = edge_tts.Communicate(text.strip()[:320], voice="fa-IR-DilaraNeural", rate="-4%", pitch="-2Hz")
            chunks = bytearray()
            async for ch in comm.stream():
                if ch.get("type") == "audio":
                    chunks.extend(ch["data"])
            return bytes(chunks)

        mp3_bytes = asyncio.run(_synth())
        if mp3_bytes:
            return "data:audio/mpeg;base64," + base64.b64encode(mp3_bytes).decode("ascii")
    except Exception:
        pass
    return ""


def _route_command(transcript: str) -> dict[str, Any]:
    t = transcript.strip()
    low = t.replace("ي", "ی").replace("ك", "ک")

    routes = [
        (("مرکز آمار", "آمار و گزارش", "گزارش گیری", "گزارش‌گیری"), "open_modal", "exec_analytics", "مرکز آمار و گزارش‌سازی باز شد."),
        (("پرس لاین", "پرس‌لاین", "حضور و غیاب", "حضورغیاب"), "open_modal", "porsline_hub", "بخش ورود پرس‌لاین و حضور و غیاب باز شد."),
        (("چرخه رویداد", "تبلیغات ایتا", "کانال ایتا", "رویدادها"), "open_modal", "event_pipeline", "چرخه رویدادها و تبلیغات کانال‌های ایتا باز شد."),
        (("دبیرخانه", "اندیکاتور", "بایگانی نامه"), "open_modal", "letter_registry", "دبیرخانه و بایگانی نامه‌ها باز شد."),
        (("سلامت داده", "یکتاسازی"), "open_modal", "data_health", "بخش سلامت و یکتاسازی داده‌ها باز شد."),
        (("تولید محتوا", "اطلاعیه جدید", "پست ایتا"), "open_modal", "media_studio", "استودیوی تولید محتوای رسانه‌ای باز شد."),
        (("تنظیمات", "پیکربندی"), "open_modal", "preferences", "پنجره تنظیمات باز شد."),
        (("حالت ارائه", "هیئت مدیره", "هیئت‌مدیره"), "boardroom", None, "حالت ارائه جلسه هیئت‌مدیره فعال شد."),
    ]
    for kws, action, target, reply in routes:
        if any(k in low for k in kws):
            return {"kind": action, "target": target, "transcript": t, "reply": reply}

    if "تم روشن" in low or "روشن بشه" in low:
        return {"kind": "set_theme", "target": "light", "transcript": t, "reply": "تم روشن فعال شد."}
    if "تم تیره" in low or "تیره بشه" in low:
        return {"kind": "set_theme", "target": "dark", "transcript": t, "reply": "تم تیره فعال شد."}
    if "سایدبار" in low and ("جمع" in low or "ببند" in low or "کوچک" in low):
        return {"kind": "toggle_sidebar", "target": True, "transcript": t, "reply": "سایدبار جمع شد."}
    if "سایدبار" in low and ("باز" in low or "گسترش" in low):
        return {"kind": "toggle_sidebar", "target": False, "transcript": t, "reply": "سایدبار باز شد."}

    smart_reply = _answer_question_concisely(t)
    return {"kind": "chat_prompt", "target": t, "transcript": t, "reply": smart_reply}


def listen_and_execute_voice(engine: str | None = None, tts_enabled: bool | None = None) -> dict[str, Any]:
    try:
        branding = load_branding()
        chosen = (engine or branding.get("voice_engine") or "gemini").lower()
        if chosen not in ("gemini", "whisper"):
            chosen = "gemini"
        want_tts = bool(branding.get("voice_tts", True)) if tts_enabled is None else bool(tts_enabled)

        ok_rec, wav_or_err = _record_wav_callback()
        if not ok_rec:
            return {"ok": False, "error": str(wav_or_err), "engine": chosen}

        wav_bytes = wav_or_err if isinstance(wav_or_err, bytes) else b""
        if chosen == "whisper":
            ok_tr, text = _whisper_transcribe(wav_bytes, str(branding.get("whisper_model") or "small"))
        else:
            ok_tr, text = _gemini_transcribe(wav_bytes)

        if not ok_tr:
            return {"ok": False, "error": text, "engine": chosen}

        routed = _route_command(text)
        routed["ok"] = True
        routed["engine"] = chosen
        routed["audio_uri"] = _persian_tts_data_uri(routed.get("reply") or "") if want_tts else ""
        return routed
    except Exception as exc:
        logger.exception("Voice copilot internal error")
        return {"ok": False, "error": f"خطای داخلی صوتی: {exc}"}


def process_voice_command(audio_b64: str, engine: str | None = None, mime_type: str = "audio/wav") -> dict[str, Any]:
    return listen_and_execute_voice(engine=engine)
