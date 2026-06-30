#!/usr/bin/env python3
"""
Hive Content Pipeline — Persistent Daemon.

Usage:
    python3 main.py run              # Start scheduler daemon
    python3 main.py status           # Show pipeline status
    python3 main.py test-post        # Test publish 1 story
    python3 main.py test-notif       # Test Telegram notification
    python3 main.py generate [n]     # Generate n new stories
"""

import sys
import os
import logging
import argparse

# Ensure src is importable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.config import config
from src import database as db

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-12s %(levelname)-5s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "pipeline.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("main")


def cmd_run():
    """Start the persistent scheduler daemon."""
    from src.scheduler import PublisherScheduler
    db.init_db()
    log.info("Starting Hive daemon...")
    scheduler = PublisherScheduler()
    scheduler.run()


def cmd_status():
    """Show pipeline status."""
    db.init_db()
    stats = db.get_stats()
    schedule_times = ", ".join(config.POST_TIMES)

    print("╔══════════════════════════════════════════════╗")
    print("║        🐝  HIVE — STATUS  🐝              ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"  ⏰  Schedule: {schedule_times} WIB")
    print(f"  📦  Story Ready: {stats['ready']}")
    print(f"  ✅  Posted: {stats['posted']}")
    print(f"  ❌  Failed: {stats['failed']}")
    print(f"  📊  Total: {stats['total_articles']} articles")
    print(f"  🤖  Auto-gen threshold: {config.STOCK_MIN}")
    print(f"  📄  Max chars: {config.MAX_CHARS:,}")
    print()


def cmd_test_post():
    """Test publish one story."""
    from src import pipeline as pline
    db.init_db()
    a = db.get_next_pending()
    if not a:
        print("❌ No stories ready to publish!")
        return
    log.info("Testing publish id=%d: %s", a["id"], a.get("story_title", "?"))
    try:
        result = pline.publish_by_id(a["id"])
        if result:
            print(f"✅ Published! post_id={result.get('post_id')}")
            print(f"   URL: {result.get('post_url', 'N/A')}")
        else:
            print("❌ Publish returned no result")
    except Exception as e:
        print(f"❌ Error: {e}")


def cmd_test_notif():
    """Test Telegram notification."""
    from src import notifier as tg
    ok = tg.notify_startup(config.POST_TIMES, db.count_stories("story_ready"))
    if ok:
        print("✅ Telegram notification sent!")
    else:
        print("❌ Telegram notification failed. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")


def cmd_generate(count: int = 3):
    """Generate new stories from scraped articles."""
    from src.storyteller import generate_story as gen_story
    import json

    db.init_db()
    scraped = db.get_articles_by_status("scraped", limit=count)
    if not scraped:
        # Try scraping some from topic bank first
        log.info("No scraped articles. Trying topic bank...")
        try:
            from src import topic_selector
            topics = topic_selector.random_from_all(count)
            if not topics:
                print("❌ Topic bank empty!")
                return
            imported = 0
            from src import pipeline as pline
            for t in topics:
                try:
                    result = pline.ingest(t["topic"])
                    if result:
                        imported += 1
                except Exception:
                    continue

            log.info("Imported %d new topics", imported)
            scraped = db.get_articles_by_status("scraped", limit=count)
        except Exception as e:
            log.error("Failed to auto-import: %s", e)

    if not scraped:
        print("❌ No topics to generate stories from!")
        return

    success = 0
    for article in scraped:
        try:
            aid = article["id"]
            topic = article.get("topic", "?")
            scraped_data = json.loads(article["scraped_json"])
            result = gen_story(scraped_data)
            if result and result.get("body"):
                db.save_story(aid, result["title"], result["body"])
                success += 1
                log.info("✅ id=%d: %s (%d chars)", aid, topic, len(result["body"]))
            else:
                log.error("❌ id=%d: Empty LLM output", aid)
        except Exception as e:
            log.error("❌ id=%d: %s", article["id"], e)

    print(f"\n📊 Generated: {success}/{len(scraped)}")
    print(f"📦 Stock ready: {db.count_stories('story_ready')}")


def main():
    parser = argparse.ArgumentParser(description="Hive Content Pipeline Daemon")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Start scheduler daemon")
    sub.add_parser("status", help="Show pipeline status")
    sub.add_parser("test-post", help="Test publish 1 story")
    sub.add_parser("test-notif", help="Test Telegram notification")

    gen_parser = sub.add_parser("generate", help="Generate new stories")
    gen_parser.add_argument("count", nargs="?", type=int, default=3, help="Number of stories")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run()
    elif args.command == "status":
        cmd_status()
    elif args.command == "test-post":
        cmd_test_post()
    elif args.command == "test-notif":
        cmd_test_notif()
    elif args.command == "generate":
        cmd_generate(args.count)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
