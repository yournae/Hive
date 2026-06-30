"""Telegram notifier for Hive Content Pipeline."""

import logging
import html
import re
import datetime
import requests
from .config import config

log = logging.getLogger(__name__)

BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
CHAT_ID = config.TELEGRAM_CHAT_ID
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None

TZ_LABEL = "WIB"  # display suffix for timestamps


def _now_str() -> str:
    """Current time 'HH:MM' in config.TIMEZONE (fallback UTC)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(getattr(config, "TIMEZONE", "Asia/Jakarta"))
        return datetime.datetime.now(tz).strftime("%H:%M")
    except Exception:
        return datetime.datetime.utcnow().strftime("%H:%M")


def _today_str() -> str:
    """Current date 'DD Mon' in config.TIMEZONE (fallback UTC)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(getattr(config, "TIMEZONE", "Asia/Jakarta"))
        return datetime.datetime.now(tz).strftime("%d %b")
    except Exception:
        return datetime.datetime.utcnow().strftime("%d %b")


def _truncate(text: str, limit: int = 60) -> str:
    """Trim long titles to keep notifications tidy."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _send(text: str, parse_mode: str = "HTML") -> bool:
    """Send message to Telegram chat. Returns True if successful."""
    if not (API_URL and CHAT_ID):
        return False
    if parse_mode == "HTML":
        text = html.escape(text, quote=False)
        # Re-allow our own <b>, <i>, <code>, <a> tags
        for tag in ("b", "i", "code", "pre", "a"):
            text = text.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;{tag} ", f"<{tag} ").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
        # Only un-escape &gt; that closes a tag (appears after a quoted attr)
        text = re.sub(r'(?<=&quot;)&gt;', '>', text)
    try:
        r = requests.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text[:4096],  # Telegram limit
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return True
        log.warning("Telegram send failed: %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("Telegram send error: %s", e)
    return False


def notify_startup(schedule_times: list, stock_count: int):
    times = ", ".join(schedule_times)
    return _send(
        f"🚀 <b>Hive Started</b> · {_now_str()} {TZ_LABEL}\n"
        f"⏰ Jadwal: {times} {TZ_LABEL}\n"
        f"📦 Stock siap: {stock_count} narasi"
    )


def notify_shutdown():
    return _send(f"🛑 <b>Hive Stopped</b> · {_now_str()} {TZ_LABEL}")


def notify_published(title: str, chars: int, url: str = None):
    """Notif post sukses (format A). chars dipertahankan utk kompatibilitas argumen."""
    # Counter harian + stock diambil dari DB → akurat utk manual & scheduler
    try:
        from . import database as db
        posted_today = db.count_posted_today()
        stock = db.count_stories("story_ready")
        stat_line = f"📊 Post #{posted_today} hari ini · stock {stock}"
    except Exception:
        stat_line = None

    msg = (
        f"✅ <b>Published</b> · {_now_str()} {TZ_LABEL}\n"
        f"📖 {_truncate(title)}"
    )
    if stat_line:
        msg += f"\n{stat_line}"
    if url:
        msg += f"\n🔗 <a href=\"{url}\">Lihat post</a>"
    return _send(msg)


def notify_error(error: str, context: str = "publish"):
    return _send(
        f"❌ <b>{context.title()} Error</b> · {_now_str()} {TZ_LABEL}\n"
        f"<code>{str(error)[:500]}</code>"
    )


def notify_generated(count: int, stock: int):
    return _send(
        f"📦 <b>Auto-Generated</b> · {_now_str()} {TZ_LABEL}\n"
        f"✅ {count} narasi baru\n"
        f"📊 Stock: {stock}"
    )


def notify_stock_warning(stock: int, generating: bool = False):
    if generating:
        return _send(
            f"⚠️ <b>Stock Low</b> ({stock} narasi) · {_now_str()} {TZ_LABEL}\n"
            f"🔄 Generating konten baru..."
        )
    else:
        return _send(
            f"⚠️ <b>Stock Critical</b> ({stock} narasi) · {_now_str()} {TZ_LABEL}\n"
            f"❌ Ga ada topik tersisa buat generate!"
        )


def notify_daily_summary(posted: int, failed: int, stock: int):
    return _send(
        f"📊 <b>Rekap Harian</b> · {_today_str()}\n"
        f"✅ Posted : {posted}\n"
        f"❌ Gagal  : {failed}\n"
        f"📦 Stock  : {stock} narasi siap"
    )
