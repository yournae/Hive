"""Persistent scheduler daemon for Hive.

Mimics threads-bot architecture:
- Posts at configurable times (08:00, 13:00, 20:00 WIB)
- Auto-generates stories when stock < STOCK_MIN
- Notifies via Telegram
- Respects rest hours (22:00 - 06:00)
- Internal daily state tracking
"""

import time
import logging
import signal
import json
import threading
from datetime import datetime
from dateutil import tz

from .config import config
from . import database as db, pipeline as pline, storyteller
from . import notifier as tg

log = logging.getLogger(__name__)

TZ = tz.gettz(config.TIMEZONE) if config.TIMEZONE else tz.gettz("Asia/Jakarta")
TICK_INTERVAL = 60  # seconds


class PublisherScheduler:
    def __init__(self):
        self.running = True
        self._stop_event = threading.Event()
        self._today = None
        self._posted_today = 0
        self._failed_today = 0
        self._tick_count = 0
        self._last_auto_generate = None  # Cooldown for auto-generate

        # Trap SIGTERM/SIGINT for clean shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, _frame):
        log.warning("Received signal %d, shutting down...", signum)
        self.running = False
        self._stop_event.set()  # wake any in-progress _sleep() immediately

    def _sleep(self, seconds):
        """Interruptible sleep. Returns immediately when stop is requested.

        Replaces time.sleep() — under PEP 475, time.sleep() auto-resumes after
        a signal if the handler doesn't raise, so Ctrl+C wouldn't break the
        loop. Event.wait() returns the instant _stop_event is set.
        """
        self._stop_event.wait(timeout=seconds)

    # ── helpers ──

    def _now(self) -> datetime:
        return datetime.now(TZ)

    def _is_rest_hours(self) -> bool:
        h = self._now().hour
        return h >= config.REST_START or h < config.REST_END

    def _reset_daily(self):
        today = self._now().date()
        if self._today != today:
            if self._today is not None:
                # Send daily summary
                stock = db.count_stories("story_ready")
                tg.notify_daily_summary(self._posted_today, self._failed_today, stock)
            self._today = today
            self._posted_today = 0
            self._failed_today = 0
            log.info("Daily counters reset: day=%s", today)

    def _check_stock(self) -> int:
        """Return count of story_ready articles."""
        return db.count_stories("story_ready")

    def _auto_generate(self):
        """Generate new stories when stock is low."""
        stock = self._check_stock()
        if stock >= config.STOCK_MIN:
            return

        # Cooldown: don't auto-generate more than once per hour
        now = self._now()
        if self._last_auto_generate:
            elapsed = (now - self._last_auto_generate).total_seconds()
            if elapsed < 3600:  # 1 hour cooldown
                log.debug("Auto-generate cooldown: %ds remaining", 3600 - elapsed)
                return

        # Set cooldown SEKARANG (sebelum cek scraped). Kalau ga, cabang
        # "no topics left" di bawah return tanpa set cooldown → tiap 5 menit
        # _auto_generate dipanggil lagi → spam notify_stock_warning ke Telegram.
        self._last_auto_generate = now

        # Get scraped articles needing stories
        scraped = db.get_articles_by_status("scraped")
        if not scraped:
            log.warning("No scraped topics to generate from!")
            tg.notify_stock_warning(stock, generating=False)
            return
        tg.notify_stock_warning(stock, generating=True)
        need = config.STOCK_MIN - stock
        to_generate = scraped[:min(need, config.BATCH_SIZE)]

        success = 0
        for article in to_generate:
            try:
                aid = article["id"]
                topic = article.get("topic", "Unknown")
                scraped_data = json.loads(article["scraped_json"])
                result = storyteller.generate_story(scraped_data)
                if result and result.get("body"):
                    db.save_story(aid, result["title"], result["body"])
                    # Also save story file to disk
                    pline._save_story_file(topic, result["title"], result["body"])
                    success += 1
                    log.info("Auto-generated story id=%d: %s (%d chars)",
                             aid, topic, len(result["body"]))
            except Exception as e:
                log.error("Auto-generate failed id=%d: %s", article["id"], e)

        if success > 0:
            new_stock = self._check_stock()
            tg.notify_generated(success, new_stock)

    def _publish_one(self) -> bool:
        """Publish one story from queue. Returns True if success."""
        article = db.get_next_pending()
        if not article:
            log.info("No pending articles to publish")
            return False

        try:
            result = pline.publish_by_id(article["id"])
            if result and result.get("post_id"):
                url = result.get("post_url", "")
                log.info("Published id=%d -> %s", article["id"], url)
                # Notif sukses sudah dikirim di pipeline._do_publish (chokepoint
                # tunggal) — jangan kirim lagi di sini biar ga dobel.
                self._posted_today += 1
                return True
            else:
                # result None = artikel sudah di-post / tidak ada story. Bukan
                # kegagalan publish, jadi tidak hitung sebagai failed & no notif.
                log.info("Publish id=%d skipped (already posted / no story)", article["id"])
                return False
        except Exception as e:
            # Notif error sudah dikirim di _do_publish; di sini cukup hitung counter.
            log.error("Publish failed id=%d: %s", article["id"], e)
            self._failed_today += 1
            return False

    # ── main loop ──

    def run(self):
        db.init_db()

        stock = self._check_stock()
        log.info("Hive Scheduler started")
        if config.SCHEDULE_MODE == "interval":
            log.info("Mode: interval (every %sh from %02d:00)",
                     config.INTERVAL_HOURS, config.START_HOUR)
        else:
            log.info("Mode: fixed")
        log.info("Post times: %s %s", config.POST_TIMES, config.TIMEZONE)
        log.info("Rest hours: %02d:00-%02d:00", config.REST_START, config.REST_END)
        log.info("Auto-generate when stock < %d", config.STOCK_MIN)
        log.info("Stock ready: %d", stock)

        tg.notify_startup(config.POST_TIMES, stock)

        # Check & generate if stock low at startup
        if stock < config.STOCK_MIN:
            self._auto_generate()

        # Track which slots we've already posted today to avoid double-post
        posted_slots_today = set()

        while self.running:
            try:
                prev_day = self._today
                self._reset_daily()

                if prev_day is not None and str(prev_day) != str(self._today):
                    posted_slots_today = set()

                # Skip during rest hours
                if self._is_rest_hours():
                    self._sleep(TICK_INTERVAL)
                    continue

                # Check if it's time to post
                now = self._now()
                now_mins = now.hour * 60 + now.minute
                for slot_idx, t_str in enumerate(config.POST_TIMES):
                    parts = t_str.strip().split(":")
                    if len(parts) == 2:
                        try:
                            hm = int(parts[0]) * 60 + int(parts[1])
                        except ValueError:
                            continue
                        if abs(now_mins - hm) <= 1:
                            slot_key = f"{self._today}_{slot_idx}_{t_str.strip()}"
                            if slot_key not in posted_slots_today:
                                log.info("Scheduled time reached (slot %s), posting...", slot_key)
                                self._publish_one()
                                posted_slots_today.add(slot_key)
                            break

                # Check stock periodically (every 5 min)
                self._tick_count += 1
                if self._tick_count % 5 == 0:
                    if self._check_stock() < config.STOCK_MIN:
                        self._auto_generate()

                # Sleep
                self._sleep(TICK_INTERVAL)

            except KeyboardInterrupt:
                log.info("Keyboard interrupt received")
                self.running = False
                self._stop_event.set()
                break
            except Exception as e:
                log.exception("Scheduler loop error: %s", e)
                tg.notify_error(str(e)[:300], "scheduler loop")
                self._sleep(TICK_INTERVAL * 2)  # back off on error

        tg.notify_shutdown()
        log.info("Hive Scheduler stopped")
