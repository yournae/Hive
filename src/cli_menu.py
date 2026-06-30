"""
Interactive CLI Menu for Hive Content Pipeline.
Nested menus: Status → Browse → Topic → Generate → Publish → System.

Usage: python3 run.py menu
"""

import os, sys, time, json, sqlite3
from datetime import datetime

# Ensure imports work
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def _clear():
    os.system("clear" if os.name != "nt" else "cls")


def _header(title, subtitle=""):
    print(f"\n╔{'═'*50}╗")
    print(f"║  {title:<48}║")
    if subtitle:
        print(f"║  {subtitle:<48}║")
    print(f"╚{'═'*50}╝\n")


def _prompt(text="Pilih", default=""):
    try:
        val = input(f"  {text} [{default}]: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _pause():
    input("\n  [Enter untuk kembali...]")


def _conn():
    from src.config import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_stats():
    from src.database import init_db
    init_db()
    conn = _conn()
    s = {}
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM articles")
    s["total"] = c.fetchone()[0]
    for st in ("scraped", "story_ready", "posted", "failed"):
        c.execute("SELECT COUNT(*) FROM articles WHERE status=?", (st,))
        s[st] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM posts WHERE status='success'")
    s["posts_success"] = c.fetchone()[0]
    conn.close()
    return s


# ═══════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════

def _check_topic_bank():
    import os
    from src.topic_bank_generator import BANK_PATH
    if not os.path.exists(BANK_PATH):
        print("  ⚠️  Topic bank belum ada!")
        do = _prompt("Generate topic bank sekarang? (y/n)", "y")
        if do and do.lower() == "y":
            _topic_generate_bank()


def main_menu():
    _check_topic_bank()
    while True:
        _clear()
        s = _get_stats()
        _header("🐝  HIVE", "Scrape → Generate → Publish")

        print(f"  📦 Total: {s['total']} | ✅ Posted: {s['posted']} | 📖 Ready: {s['story_ready']}")
        print(f"  📝 Scraped: {s['scraped']} | ❌ Failed: {s['failed']}")
        print()
        print("  1) 📊  Status & Statistik")
        print("  2) 🔍  Browse Artikel")
        print("  3) 🎯  Pilih Topik")
        print("  4) 📝  Generate Story")
        print("  5) 📤  Publish ke Facebook")
        print("  6) 🔧  System & Tools")
        print()
        print("  0)  Keluar")

        ch = _prompt("Pilih menu")

        if ch in (None, "0"):
            print("\n  👋 Bye!\n")
            break
        elif ch == "1":
            menu_status()
        elif ch == "2":
            menu_browse()
        elif ch == "3":
            menu_topic()
        elif ch == "4":
            menu_generate()
        elif ch == "5":
            menu_publish()
        elif ch == "6":
            menu_system()


# ═══════════════════════════════════════════════════════════════
# 1) STATUS & STATS
# ═══════════════════════════════════════════════════════════════

def menu_status():
    _clear()
    _header("📊  Status & Statistik")

    from src.config import config
    s = _get_stats()

    print(f"  ⏰  Schedule: {', '.join(config.POST_TIMES)} WIB")
    print(f"  🌍  Timezone: {config.TIMEZONE}")
    print(f"  🤖  LLM: {config.primary_model()} ({config.LLM_PROVIDER_COUNT} slot)")
    print(f"  📏  Max chars: {config.MAX_CHARS:,}")
    print(f"  🔑  FB Token: {'✅ Set' if config.FB_PAGE_TOKEN else '❌ Missing'}")
    print(f"  📢  Telegram: {'✅ Set' if config.TELEGRAM_BOT_TOKEN else '❌ Not set'}")
    print()
    print(f"  ┌─────────────────────────────────────┐")
    print(f"  │  Status          │  Jumlah           │")
    print(f"  ├──────────────────┼───────────────────┤")
    print(f"  │  📝 Scraped      │  {s['scraped']:>6}           │")
    print(f"  │  📖 Story Ready  │  {s['story_ready']:>6}           │")
    print(f"  │  ✅ Posted       │  {s['posted']:>6}           │")
    print(f"  │  ❌ Failed       │  {s['failed']:>6}           │")
    print(f"  │  📦 Total        │  {s['total']:>6}           │")
    print(f"  └─────────────────────────────────────┘")

    # Show char length distribution of ready stories
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, topic, LENGTH(story_body) as len FROM articles WHERE status='story_ready' ORDER BY id")
    rows = c.fetchall()
    if rows:
        print(f"\n  📖 Story siap posting:")
        for r in rows:
            flag = " ⚠️ OVER LIMIT" if r["len"] > config.MAX_CHARS else ""
            print(f"     id={r['id']:>3} | {r['len']:>7,} chars | {r['topic'][:35]}{flag}")

    # Show recent posts
    c.execute("SELECT p.posted_at, a.topic FROM posts p LEFT JOIN articles a ON p.article_id=a.id WHERE p.status='success' ORDER BY p.posted_at DESC LIMIT 3")
    rows = c.fetchall()
    if rows:
        print(f"\n  📤 Post terakhir:")
        for r in rows:
            ts = r["posted_at"][:16] if r["posted_at"] else "?"
            print(f"     {ts} | {r['topic'][:40]}")
    conn.close()

    _pause()


# ═══════════════════════════════════════════════════════════════
# 2) BROWSE ARTICLES
# ═══════════════════════════════════════════════════════════════

def menu_browse():
    while True:
        _clear()
        _header("🔍  Browse Artikel")

        print("  1) 📋  Semua artikel")
        print("  2) 📖  Story siap post (story_ready)")
        print("  3) 📝  Sudah di-scrape, belum ada story")
        print("  4) ✅  Sudah di-post")
        print("  5) ❌  Gagal")
        print("  6) 🔎  Cari by ID")
        print("  7) 🗑️  Hapus artikel")
        print()
        print("  0) ← Kembali")

        ch = _prompt("Pilih")

        if ch in (None, "0"):
            break
        elif ch in ("1", "2", "3", "4", "5"):
            status_map = {"1": None, "2": "story_ready", "3": "scraped", "4": "posted", "5": "failed"}
            _show_articles(status_map[ch])
        elif ch == "6":
            _browse_by_id()
        elif ch == "7":
            _browse_delete()


def _show_articles(status=None):
    _clear()
    conn = _conn()
    c = conn.cursor()
    if status:
        c.execute("SELECT id, topic, title, status, LENGTH(story_body) as len FROM articles WHERE status=? ORDER BY id", (status,))
    else:
        c.execute("SELECT id, topic, title, status, LENGTH(story_body) as len FROM articles ORDER BY id")
    rows = c.fetchall()
    conn.close()

    label = status or "semua"
    _header(f"📋  Artikel ({label})")

    if not rows:
        print("  (kosong)")
        _pause()
        return

    print(f"  {'ID':>4}  {'Status':<14} {'Chars':>8}  {'Topik'}")
    print(f"  {'─'*4}  {'─'*14} {'─'*8}  {'─'*35}")
    for r in rows:
        icon = {"posted": "✅", "story_ready": "📖", "scraped": "📝", "failed": "❌"}.get(r["status"], "❓")
        chars = f"{r['len']:>7,}" if r["len"] else "    —"
        print(f"  {r['id']:>4}  {icon} {r['status']:<12} {chars}  {r['topic'][:40]}")

    print(f"\n  Total: {len(rows)} artikel")
    _pause()


def _browse_by_id():
    aid = _prompt("Masukkan article ID")
    if aid is None or not aid.isdigit():
        print("  ❌ ID harus angka"); _pause(); return

    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE id=?", (int(aid),))
    r = c.fetchone()
    conn.close()

    if not r:
        print(f"  ❌ Artikel id={aid} tidak ditemukan"); _pause(); return

    _clear()
    _header(f"📖  Artikel #{r['id']}")

    print(f"  Topik:     {r['topic']}")
    print(f"  Judul:     {r['title'] or '—'}")
    print(f"  Status:    {r['status']}")
    print(f"  Source:    {r['source_url'] or '—'}")
    if r["story_title"]:
        print(f"  Story:     {r['story_title']}")
    if r["story_body"]:
        print(f"  Chars:     {len(r['story_body']):,}")
    print()

    if r["story_body"]:
        preview = r["story_body"][:500].replace("\n", "\n  ")
        print(f"  --- Preview ---")
        print(f"  {preview}...")
        print(f"  ---")

    _pause()


def _browse_delete():
    aid = _prompt("Article ID untuk dihapus")
    if aid is None or not aid.isdigit():
        print("  ❌ ID harus angka"); _pause(); return

    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, topic, status FROM articles WHERE id=?", (int(aid),))
    r = c.fetchone()
    conn.close()

    if not r:
        print(f"  ❌ Artikel id={aid} tidak ditemukan"); _pause(); return

    print(f"\n  id={r['id']} | {r['status']} | {r['topic']}")
    confirm = _prompt(f"⚠️  Hapus permanen? (y/n)", "n")
    if confirm is None or confirm.lower() != "y":
        print("  Dibatalkan."); _pause(); return

    from src import database as db
    ok = db.delete_article(int(aid))
    print(f"  ✅ id={aid} dihapus." if ok else f"  ❌ Gagal hapus.")
    _pause()


# ═══════════════════════════════════════════════════════════════
# 3) TOPIC SELECTION
# ═══════════════════════════════════════════════════════════════

def menu_topic():
    while True:
        _clear()
        _header("🎯  Pilih Topik", "Topic Bank → Scrape Wikipedia → Simpan ke DB")

        print("  1) 🎲  Random 1 topik (dari kategori)")
        print("  2) 🎰  Random N topik (batch)")
        print("  3) 🍀  Random dari semua kategori (luck)")
        print("  4) 🔤  Scrape topik manual")
        print("  5) 📂  Lihat semua kategori")
        print("  6) 🔄  Generate Topic Bank (fresh)")
        print()
        print("  0) ← Kembali")

        ch = _prompt("Pilih")

        if ch in (None, "0"):
            break
        elif ch == "1":
            _topic_random()
        elif ch == "2":
            _topic_batch()
        elif ch == "3":
            _topic_luck()
        elif ch == "4":
            _topic_manual()
        elif ch == "5":
            _topic_categories()
        elif ch == "6":
            _topic_generate_bank()


def _pick_category():
    """Show category list and return chosen key."""
    from src import topic_selector
    cats = topic_selector.list_categories()
    print("\n  Kategori:")
    for i, c in enumerate(cats, 1):
        print(f"    {i}) {c['id']:<18} {c['description'][:30]:<30} ({c['count']} topik)")
    print()
    idx = _prompt("Nomor kategori")
    if idx is not None and idx.isdigit() and 1 <= int(idx) <= len(cats):
        return cats[int(idx) - 1]["id"]
    return None


def _topic_random():
    from src import topic_selector
    cat = _pick_category()
    if not cat:
        print("  ❌ Kategori tidak valid"); _pause(); return

    t = topic_selector.random_topic(cat)
    _clear()
    _header(f"🎲  Random: {t['category']}")
    print(f"  Topik:       {t['topic']}")
    print(f"  Tags:        {', '.join(t['tags'])}")
    if t["notes"]:
        print(f"  Catatan:     {t['notes']}")

    print()
    do = _prompt("Scrape topik ini? (y/n)", "n")
    if do is not None and do.lower() == "y":
        from src import pipeline
        result = pipeline.ingest(t["topic"], t.get("url"))
        aid = result.get("id") if result else None
        if aid:
            print(f"  ✅ Scraped! article_id={aid}")
        else:
            print(f"  ⚠️  Sudah ada di database.")
    _pause()


def _topic_batch():
    from src import topic_selector
    cat = _pick_category()
    if not cat:
        print("  ❌ Kategori tidak valid"); _pause(); return

    n = _prompt("Jumlah topik", "3")
    if n is None:
        return
    n = int(n) if n.isdigit() else 3

    batch = topic_selector.random_batch(cat, n)
    _clear()
    _header(f"🎰  Batch: {batch['category']} ({batch['count']} topik)")

    for i, t in enumerate(batch["topics"], 1):
        print(f"  {i}. {t['topic']}")
        if t["notes"]:
            print(f"     {t['notes']}")
    print()

    do = _prompt("Scrape semua? (y/n)", "n")
    if do is not None and do.lower() == "y":
        from src import pipeline
        ok = 0
        for t in batch["topics"]:
            try:
                result = pipeline.ingest(t["topic"], t.get("url"))
                aid = result.get("id") if result else None
                if aid:
                    ok += 1
                    print(f"  ✅ {t['topic']} → id={aid}")
                else:
                    print(f"  ⏭️  {t['topic']} → sudah ada")
                time.sleep(2)
            except Exception as e:
                print(f"  ❌ {t['topic']} → {e}")
        print(f"\n  📦 Scraped: {ok}/{batch['count']}")
    _pause()


def _topic_luck():
    from src import topic_selector
    n = _prompt("Jumlah topik", "3")
    if n is None:
        return
    n = int(n) if n.isdigit() else 3

    topics = topic_selector.random_from_all(n)
    _clear()
    _header(f"🍀  Luck! ({len(topics)} topik)")

    for i, t in enumerate(topics, 1):
        print(f"  {i}. [{t['category'][:20]}] {t['topic']}")
    print()

    do = _prompt("Scrape semua? (y/n)", "n")
    if do is not None and do.lower() == "y":
        from src import pipeline
        ok = 0
        for t in topics:
            try:
                result = pipeline.ingest(t["topic"], t.get("url"))
                aid = result.get("id") if result else None
                if aid:
                    ok += 1
                    print(f"  ✅ {t['topic']} → id={aid}")
                else:
                    print(f"  ⏭️  {t['topic']} → sudah ada")
                time.sleep(2)
            except Exception as e:
                print(f"  ❌ {t['topic']} → {e}")
        print(f"\n  📦 Scraped: {ok}/{len(topics)}")
    _pause()


def _topic_manual():
    _clear()
    _header("🔤  Scrape Topik Manual")
    topic = _prompt("Nama topik (Wikipedia)")
    if not topic:
        print("  ❌ Nama topik tidak boleh kosong.")
        _pause()
        return
    url = _prompt("URL Wikipedia (kosong = auto-cari)", "")
    if url is None:
        return
    from src import pipeline
    print(f"\n  🔍 Scraping '{topic}'...")
    try:
        result = pipeline.ingest(topic, url or None)
        aid = result.get("id") if result else None
        if aid:
            print(f"  ✅ Berhasil! article_id={aid}")
            print(f"     Jalankan Generate Story untuk membuat konten.")
        else:
            print(f"  ⚠️  Topik sudah ada di database.")
    except Exception as e:
        print(f"  ❌ Gagal: {e}")
    _pause()


def _topic_categories():
    from src import topic_selector
    cats = topic_selector.list_categories()
    _clear()
    _header("📂  Topic Bank (6 Kategori)")

    total = 0
    for c in cats:
        total += c["count"]
        print(f"  {c['id']:<20} {c['description'][:30]:<32} {c['count']:>4} topik")
    print(f"  {'─'*60}")
    print(f"  {'TOTAL':<52} {total:>4} topik")

    _pause()


def _topic_generate_bank():
    """Generate topic bank using LLM."""
    _clear()
    _header("🔄  Generate Topic Bank", "Generate topik random via LLM → data/topic_bank.yaml")

    from src.topic_bank_generator import BANK_PATH
    import os

    if os.path.exists(BANK_PATH):
        do = _prompt("Topic bank sudah ada. Regenerate? (y/n)", "n")
        if do is None or do.lower() != "y":
            return

    count = _prompt("Jumlah per kategori", "175")
    if count is None:
        return
    count = int(count) if count.isdigit() else 175

    print(f"\n  ⏳ Generating {count} topics × 6 kategori = ~{count * 6} total...")
    print("  Ini butuh beberapa menit. Tunggu...\n")

    from src.topic_bank_generator import generate_topic_bank
    import logging
    logging.basicConfig(level=logging.INFO, format="  %(message)s")

    ok, msg = generate_topic_bank(count_per_category=count)
    if ok:
        print(f"\n  ✅ {msg}")
    else:
        print(f"\n  ❌ {msg}")

    _pause()


# ═══════════════════════════════════════════════════════════════
# 4) GENERATE STORIES
# ═══════════════════════════════════════════════════════════════

def menu_generate():
    while True:
        _clear()
        _header("📝  Generate Story", "Scraped Article → LLM Story (35K-55K chars)")

        conn = _conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM articles WHERE status='scraped'")
        scraped_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM articles WHERE status='story_ready'")
        ready_count = c.fetchone()[0]
        conn.close()

        print(f"  📝 Menunggu story: {scraped_count}")
        print(f"  📖 Story siap:     {ready_count}")
        print()
        print("  1) 🤖  Generate 1 story (by ID)")
        print("  2) 📦  Generate batch (dari yang scraped)")
        print("  3) 🔄  Scrape + Generate sekaligus")
        print("  4) 🧹  Non-Latin Cleaner (hapus karakter CJK, Arab, Thai, dll)")
        print("  5) 🔄  Re-generate story (quality retry)")
        print()
        print("  0) ← Kembali")

        ch = _prompt("Pilih")

        if ch in (None, "0"):
            break
        elif ch == "1":
            _generate_by_id()
        elif ch == "2":
            _generate_batch()
        elif ch == "3":
            _generate_scrape_and_gen()
        elif ch == "4":
            _generate_cjk_clean()
        elif ch == "5":
            _generate_regenerate()


def _generate_by_id():
    # Show available scraped articles first
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, topic, LENGTH(story_body) as len FROM articles WHERE status='scraped' ORDER BY id")
    rows = c.fetchall()
    conn.close()

    if rows:
        print("\n  📝 Artikel menunggu story:")
        print(f"  {'ID':>4}  {'Chars':>7}  {'Topik'}")
        print(f"  {'─'*4}  {'─'*7}  {'─'*35}")
        for r in rows:
            print(f"  {r['id']:>4}  {'—':>7}  {r['topic'][:40]}")
        print(f"  Total: {len(rows)} artikel")
    else:
        conn2 = _conn(); c2 = conn2.cursor()
        c2.execute("SELECT COUNT(*) FROM articles")
        total = c2.fetchone()[0]; conn2.close()
        if total == 0:
            print("\n  📭 Belum ada artikel. Pilih Topik → Scrape dulu.")
        else:
            print("\n  ✅ Semua artikel sudah punya story!")
        _pause(); return

    aid = _prompt("\n  Article ID")
    if aid is None or not aid.isdigit():
        print("  ❌ ID harus angka"); _pause(); return

    from src import pipeline
    print(f"\n  🤖 Generating story id={aid}...")
    try:
        s = pipeline.make_story(int(aid))
        chars = len(s["body"])
        print(f"  ✅ Story generated! {chars:,} karakter")
        print(f"  Judul: {s['title'][:60]}")
        print(f"  📁 Saved: data/stories/ + database")
        from src.config import config as _cfg
        if chars > _cfg.MAX_CHARS:
            print(f"  ⚠️  OVER {_cfg.MAX_CHARS:,}! Akan dipotong saat publish.")
    except Exception as e:
        print(f"  ❌ Gagal: {e}")
    _pause()


def _generate_batch():
    n = _prompt("Jumlah story", "3")
    if n is None:
        return
    n = int(n) if n.isdigit() else 3

    from src import database as db
    from src import pipeline as pline
    from src.storyteller import generate_story
    import json

    scraped = db.get_articles_by_status("scraped", limit=n)
    if not scraped:
        print("  ❌ Tidak ada artikel scraped. Scrape topik dulu!")
        _pause(); return

    print(f"\n  📦 Generating {len(scraped)} stories...\n")
    ok = 0
    for a in scraped:
        aid = a["id"]
        topic = a.get("topic", "?")
        try:
            data = json.loads(a["scraped_json"])
            result = generate_story(data)
            if result and result.get("body"):
                db.save_story(aid, result["title"], result["body"])
                # Save story file to disk (so it appears in data/stories/)
                pline._save_story_file(topic, result["title"], result["body"])
                chars = len(result["body"])
                print(f"  ✅ id={aid} {topic[:35]:<35} {chars:>7,} chars")
                ok += 1
            else:
                print(f"  ❌ id={aid} {topic[:35]:<35} LLM output kosong")
        except Exception as e:
            print(f"  ❌ id={aid} {topic[:35]:<35} {str(e)[:40]}")

    print(f"\n  📊 Generated: {ok}/{len(scraped)}")
    print(f"  📦 Total siap: {db.count_stories('story_ready')}")
    _pause()


def _generate_scrape_and_gen():
    _clear()
    _header("🔄  Scrape + Generate")
    topic = _prompt("Nama topik")
    if not topic:
        return

    from src import pipeline, database as db
    print(f"\n  🔍 Scraping '{topic}'...")
    try:
        aid = pipeline.add(topic)
        if aid:
            print(f"  ✅ Done! article_id={aid}")
            a = db.get_article(aid)
            if a and a.get("story_body"):
                print(f"  📖 Story: {len(a['story_body']):,} chars")
        else:
            print(f"  ⚠️  Topik sudah ada.")
    except Exception as e:
        print(f"  ❌ Gagal: {e}")
    _pause()


def _generate_cjk_clean():
    script = os.path.join(BASE_DIR, "scripts", "clean_cjk.py")
    if not os.path.exists(script):
        print("  ❌ scripts/clean_cjk.py tidak ditemukan"); _pause(); return

    print("\n  🧹 Running CJK cleaner...")
    import subprocess
    subprocess.run(["python3", script], cwd=BASE_DIR)
    _pause()


def _generate_regenerate():
    from src import database as db
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, topic, LENGTH(story_body) as len FROM articles WHERE status IN ('story_ready','posted') ORDER BY id")
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("\n  ❌ Tidak ada artikel dengan story.")
        _pause(); return

    print("\n  📖 Artikel yang bisa di-re-generate:")
    print(f"  {'ID':>4}  {'Chars':>7}  {'Topik'}")
    print(f"  {'─'*4}  {'─'*7}  {'─'*35}")
    for r in rows:
        print(f"  {r['id']:>4}  {r['len']:>7,}  {r['topic'][:40]}")

    aid = _prompt("\n  Article ID")
    if aid is None or not aid.isdigit():
        print("  ❌ ID harus angka"); _pause(); return

    from src import pipeline
    print(f"\n  🔄 Re-generating story id={aid}...")
    try:
        s = pipeline.make_story(int(aid))
        chars = len(s["body"])
        print(f"  ✅ Story di-generate ulang! {chars:,} karakter")
        print(f"  Judul: {s['title'][:60]}")
        from src.config import config as _cfg
        if chars > _cfg.MAX_CHARS:
            print(f"  ⚠️  OVER {_cfg.MAX_CHARS:,}! Akan dipotong saat publish.")
    except Exception as e:
        print(f"  ❌ Gagal: {e}")
    _pause()


# ═══════════════════════════════════════════════════════════════
# 5) PUBLISH KE FACEBOOK
# ═══════════════════════════════════════════════════════════════

def menu_publish():
    while True:
        _clear()
        _header("📤  Publish ke Facebook")

        conn = _conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM articles WHERE status='story_ready'")
        ready = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM articles WHERE status='posted'")
        posted = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM articles WHERE status='failed'")
        failed = c.fetchone()[0]
        conn.close()

        print(f"  📖 Siap post: {ready} | ✅ Posted: {posted} | ❌ Failed: {failed}")
        print()
        print("  1) 📤  Publish 1 (next dari queue)")
        print("  2) 🎯  Publish by ID")
        print("  3) 📦  Publish batch")
        print("  4) 📜  Lihat post terakhir di FB")
        print("  5) 🔑  Cek FB Token")
        print("  6) 🔄  Reset failed → story_ready")
        print("  7) 📅  Preview jadwal posting")
        print()
        print("  0) ← Kembali")

        ch = _prompt("Pilih")

        if ch in (None, "0"):
            break
        elif ch == "1":
            _publish_next()
        elif ch == "2":
            _publish_by_id()
        elif ch == "3":
            _publish_batch()
        elif ch == "4":
            _publish_recent()
        elif ch == "5":
            _publish_check_token()
        elif ch == "6":
            _publish_reset_failed()
        elif ch == "7":
            _publish_preview()


def _publish_next():
    from src import pipeline
    print("\n  📤 Publishing next article...")
    try:
        result = pipeline.publish_next()
        if result:
            print(f"  ✅ Posted!")
            print(f"  🔗 {result.get('post_url', 'N/A')}")
        else:
            print("  ⚠️  Antrian kosong. Generate story dulu!")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    _pause()


def _publish_by_id():
    # Tampilkan dulu artikel yang SIAP di-post (story_ready) biar gampang pilih ID.
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, story_title, topic, LENGTH(story_body) AS len "
              "FROM articles WHERE status='story_ready' ORDER BY id")
    rows = c.fetchall()
    conn.close()

    if rows:
        print("\n  📖 Artikel siap di-post:")
        print(f"  {'ID':>4}  {'Chars':>7}  {'Judul / Topik'}")
        print(f"  {'─'*4}  {'─'*7}  {'─'*40}")
        for r in rows:
            judul = (r["story_title"] or r["topic"] or "?")[:45]
            ln = r["len"] if r["len"] is not None else 0
            print(f"  {r['id']:>4}  {ln:>7,}  {judul}")
        print(f"  Total: {len(rows)} artikel siap post")
    else:
        print("\n  📭 Tidak ada artikel siap di-post. Generate story dulu (status: story_ready).")
        _pause(); return

    aid = _prompt("\n  Article ID")
    if aid is None or not aid.isdigit():
        print("  ❌ ID harus angka"); _pause(); return

    from src import pipeline
    print(f"\n  📤 Publishing id={aid}...")
    try:
        result = pipeline.publish_by_id(int(aid))
        if result:
            print(f"  ✅ Posted!")
            print(f"  🔗 {result.get('post_url', 'N/A')}")
        else:
            print(f"  ⚠️  id={aid} sudah di-post atau tidak ada.")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    _pause()


def _publish_batch():
    n = _prompt("Jumlah post", "3")
    if n is None:
        return
    n = int(n) if n.isdigit() else 3

    from src import pipeline
    print(f"\n  📦 Publishing {n} articles...\n")
    ok = 0
    for i in range(n):
        try:
            result = pipeline.publish_next()
            if result:
                print(f"  ✅ [{i+1}/{n}] {result.get('post_url', 'N/A')}")
                ok += 1
            else:
                print(f"  ⚠️  Antrian kosong di post #{i+1}")
                break
        except Exception as e:
            print(f"  ❌ [{i+1}/{n}] {e}")

    print(f"\n  📊 Published: {ok}/{n}")
    _pause()


def _publish_recent():
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT p.fb_post_id, p.post_url, p.posted_at, a.topic
                 FROM posts p LEFT JOIN articles a ON p.article_id=a.id
                 WHERE p.status='success'
                 ORDER BY p.posted_at DESC LIMIT 10""")
    rows = c.fetchall()
    conn.close()

    _clear()
    _header("📜  Post Terakhir di Facebook")

    if not rows:
        print("  (belum ada post)")
        _pause(); return

    for r in rows:
        ts = r["posted_at"][:16] if r["posted_at"] else "?"
        url = r["post_url"] or "—"
        print(f"  {ts} | {r['topic'][:35]}")
        print(f"           🔗 {url}")
    _pause()


def _publish_check_token():
    from src import publisher
    _clear()
    _header("🔑  Cek FB Token")

    try:
        data = publisher.validate_token()
        print(f"  ✅ Token valid!")
        print(f"  Type:     {data.get('type', '?')}")
        print(f"  App ID:   {data.get('app_id', '?')}")
        print(f"  Scopes:   {', '.join(data.get('scopes', []))}")
        expires = data.get("expires_at", 0)
        if expires:
            from datetime import datetime
            dt = datetime.fromtimestamp(expires)
            print(f"  Expires:  {dt.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"  ❌ Token error: {e}")
    _pause()


def _publish_reset_failed():
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM articles WHERE status='failed'")
    count = c.fetchone()[0]
    if count == 0:
        print("  ✅ Tidak ada artikel yang failed.")
        conn.close(); _pause(); return

    confirm = _prompt(f"Reset {count} failed articles → story_ready? (y/n)", "n")
    if confirm is not None and confirm.lower() == "y":
        c.execute("UPDATE articles SET status='story_ready' WHERE status='failed'")
        conn.commit()
        print(f"  ✅ {count} articles di-reset ke story_ready.")
    conn.close()
    _pause()


def _publish_preview():
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, topic, LENGTH(story_body) as len FROM articles WHERE status='story_ready' ORDER BY id LIMIT 20")
    rows = c.fetchall()
    conn.close()

    _clear()
    _header("📅  Jadwal Posting Berikutnya")

    if not rows:
        print("  (kosong — generate story dulu)")
        _pause(); return

    print(f"  {'#':>3}  {'ID':>4}  {'Chars':>7}  {'Topik'}")
    print(f"  {'─'*3}  {'─'*4}  {'─'*7}  {'─'*35}")
    for i, r in enumerate(rows, 1):
        from src.config import config as _chk
        over = " ⚠️" if r["len"] and r["len"] > _chk.MAX_CHARS else ""
        print(f"  {i:>3}  {r['id']:>4}  {r['len']:>7,}  {r['topic'][:40]}{over}")
    print(f"\n  Menampilkan {len(rows)} dari antrian. Urutan = publish order.")
    _pause()


# ═══════════════════════════════════════════════════════════════
# 6) SYSTEM & TOOLS
# ═══════════════════════════════════════════════════════════════

SYSTEMD_SERVICE = "fb-pipeline.service"


def _need_sudo():
    """True if we're not root (worker runs as non-root → systemd needs privilege)."""
    import os
    return os.geteuid() != 0


def _systemctl(action):
    """Run a privileged systemctl action on the scheduler service.

    Returns (ok, output). As non-root, uses `sudo -n` (non-interactive) so the
    menu never hangs on a password prompt; if NOPASSWD sudoers isn't set up it
    returns a clear error + setup hint instead of blocking on a polkit/sudo
    password dialog.
    """
    import subprocess
    base = ["systemctl", action, SYSTEMD_SERVICE]
    cmd = (["sudo", "-n"] + base) if _need_sudo() else base
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        if r.returncode != 0 and _need_sudo() and (
            "a password is required" in out.lower()
            or "sudo: a terminal is required" in out.lower()
            or "no tty present" in out.lower()
        ):
            hint = (
                "perlu hak akses root. Set NOPASSWD sekali (aman, scoped):\n"
                f"     echo \"$USER ALL=(root) NOPASSWD: /usr/bin/systemctl * {SYSTEMD_SERVICE}\" "
                f"| sudo tee /etc/sudoers.d/fb-pipeline\n"
                f"     sudo chmod 440 /etc/sudoers.d/fb-pipeline\n"
                f"   Atau jalankan manual: sudo systemctl {action} {SYSTEMD_SERVICE}"
            )
            return False, hint
        return r.returncode == 0, out
    except Exception as e:
        return False, str(e)


def _expected_unit_text():
    """Build the systemd unit text from THIS install's actual paths.

    Portable: derives project dir, venv python, .env and log paths from the
    running checkout — works for any clone location / user (master root,
    worker ubuntu, future clones) with zero hardcoding.
    """
    import sys, os
    proj = BASE_DIR
    # venv python that's actually running this menu (sys.executable), else local venv
    py = sys.executable
    local_venv = os.path.join(proj, "venv", "bin", "python3")
    if os.path.exists(local_venv):
        py = local_venv
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "root"
    desc = "FB Content Pipeline — Auto-post Scheduler"
    return f"""[Unit]
Description={desc}
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={proj}
EnvironmentFile={os.path.join(proj, '.env')}
ExecStart={py} {os.path.join(proj, 'main.py')} run
Restart=always
RestartSec=30
StandardOutput=append:{os.path.join(proj, 'logs', 'systemd.log')}
StandardError=append:{os.path.join(proj, 'logs', 'systemd_err.log')}
SyslogIdentifier=fb-pipeline

[Install]
WantedBy=multi-user.target
"""


def _unit_path():
    return f"/etc/systemd/system/{SYSTEMD_SERVICE}"


def _unit_needs_install():
    """Return (needs_install, reason). True if unit missing or paths mismatch this checkout."""
    import os
    path = _unit_path()
    if not os.path.exists(path):
        return True, "service belum terpasang"
    try:
        with open(path, "r", encoding="utf-8") as f:
            current = f.read()
    except Exception:
        return True, "service ga kebaca"
    # key check: does ExecStart point at THIS project dir?
    if f"WorkingDirectory={BASE_DIR}\n" not in current:
        return True, f"path service ga cocok (harusnya {BASE_DIR})"
    if f"{os.path.join(BASE_DIR, 'main.py')} run" not in current:
        return True, "ExecStart path ga cocok"
    return False, "ok"


def _install_unit():
    """Write/repair the systemd unit for THIS checkout, then daemon-reload.

    Returns (ok, output). Needs root or NOPASSWD sudo (uses tee + sudo -n).
    """
    import os, subprocess, tempfile
    text = _expected_unit_text()
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
    # write via temp file then move with privilege
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".service", delete=False,
                                         encoding="utf-8") as tf:
            tf.write(text)
            tmp = tf.name
    except Exception as e:
        return False, f"gagal nulis temp unit: {e}"

    def _priv(cmd):
        full = (["sudo", "-n"] + cmd) if _need_sudo() else cmd
        r = subprocess.run(full, capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    ok, out = _priv(["cp", tmp, _unit_path()])
    try:
        os.unlink(tmp)
    except Exception:
        pass
    if not ok:
        if _need_sudo() and ("password is required" in out.lower() or "no tty" in out.lower()):
            return False, (
                "perlu root. Set NOPASSWD sekali:\n"
                f"     echo \"$USER ALL=(root) NOPASSWD: /usr/bin/systemctl * {SYSTEMD_SERVICE}, /bin/cp\" "
                "| sudo tee /etc/sudoers.d/fb-pipeline && sudo chmod 440 /etc/sudoers.d/fb-pipeline\n"
                "   Atau pasang manual unit dari output 'Lihat unit yang benar'."
            )
        return False, f"gagal pasang unit: {out}"
    ok2, out2 = _priv(["systemctl", "daemon-reload"])
    if not ok2:
        return False, f"unit terpasang tapi daemon-reload gagal: {out2}"
    return True, "unit terpasang + daemon-reload OK"


def _daemon_status():
    """Return ('active'|'inactive'|'failed'|'unknown', enabled_bool)."""
    import subprocess
    try:
        a = subprocess.run(["systemctl", "is-active", SYSTEMD_SERVICE],
                           capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        a = "unknown"
    try:
        e = subprocess.run(["systemctl", "is-enabled", SYSTEMD_SERVICE],
                           capture_output=True, text=True, timeout=10).stdout.strip()
        enabled = (e == "enabled")
    except Exception:
        enabled = False
    return a, enabled


def _reload_config_module():
    """Re-import config so the menu reflects freshly-saved config.yaml."""
    import importlib
    from src import config as _cfgmod
    importlib.reload(_cfgmod)
    return _cfgmod.config


def menu_scheduler():
    while True:
        _clear()
        _header("⏰  Scheduler", "Pengaturan jadwal posting + daemon")

        cfg = _reload_config_module()
        active, enabled = _daemon_status()
        status_icon = {"active": "🟢 RUNNING", "inactive": "⚪ STOPPED",
                       "failed": "🔴 FAILED"}.get(active, f"❓ {active}")
        boot = "✅ auto-start saat boot" if enabled else "❌ tidak auto-start"

        mode = cfg.SCHEDULE_MODE
        if mode == "interval":
            mode_desc = f"interval (tiap {cfg.INTERVAL_HOURS} jam, mulai {cfg.START_HOUR:02d}:00)"
        else:
            mode_desc = "fixed (jam tetap)"

        print(f"  Status daemon : {status_icon}   ({boot})")
        needs_unit, unit_reason = _unit_needs_install()
        if needs_unit:
            print(f"  ⚠️  Service    : {unit_reason} → pilih 'i' buat pasang/perbaiki")
        print(f"  Mode          : {mode_desc}")
        print(f"  Jam post      : {', '.join(cfg.POST_TIMES)}")
        print(f"  Timezone      : {cfg.TIMEZONE}")
        print(f"  Rest hours    : {cfg.REST_START:02d}:00 – {cfg.REST_END:02d}:00 (tidak post)")
        print(f"  Auto-generate : stock < {cfg.STOCK_MIN}, batch {cfg.BATCH_SIZE}")
        print(f"  {'─'*48}")
        print("  1) 🔀  Ganti mode (fixed ⇄ interval)")
        print("  2) 🕐  Atur jam post / interval")
        print("  3) 😴  Atur rest hours")
        print("  4) 📦  Atur auto-generate (stock/batch)")
        print("  5) 🌏  Atur timezone")
        print(f"  {'─'*48}")
        print("  6) ▶️   Start daemon (persistent, survive close/reboot)")
        print("  7) ⏹️   Stop daemon")
        print("  8) 🔄  Restart daemon (apply config baru)")
        print("  9) 📜  Lihat log daemon (live)")
        print("  i) 🔧  Install/perbaiki service (auto-detect path)")
        print("  f) 🐞  Run foreground (debug, Ctrl+C stop) ")
        print()
        print("  0) ← Kembali")

        ch = _prompt("Pilih")

        if ch in (None, "0"):
            break
        elif ch == "1":
            _sched_set_mode(cfg)
        elif ch == "2":
            _sched_set_times(cfg)
        elif ch == "3":
            _sched_set_rest(cfg)
        elif ch == "4":
            _sched_set_autogen(cfg)
        elif ch == "5":
            _sched_set_tz(cfg)
        elif ch == "6":
            _sched_daemon_start()
        elif ch == "7":
            _sched_daemon_stop()
        elif ch == "8":
            _sched_daemon_restart()
        elif ch == "9":
            _sched_daemon_logs()
        elif ch == "i":
            _sched_install_unit()
        elif ch == "f":
            print("\n  🐞 Foreground mode (Ctrl+C untuk stop)...")
            print("  ⚠️  Ini mati saat lo tutup SSH. Buat persistent pakai opsi 6.")
            _pause()
            from src.scheduler import PublisherScheduler
            from src import database as db
            db.init_db()
            PublisherScheduler().run()


def _sched_set_mode(cfg):
    from src import config_writer as cw
    if not cw.comments_preserved():
        print("\n  ⚠️  ruamel.yaml ga keinstall — komentar di config.yaml bakal ilang.")
        print("     Install biar aman: venv/bin/pip install ruamel.yaml")
    new = "interval" if cfg.SCHEDULE_MODE == "fixed" else "fixed"
    cw.set_mode(new)
    print(f"\n  ✅ Mode → {new}")
    if new == "interval":
        print("  ℹ️  Jam post akan di-generate dari interval. Atur di menu '2'.")
    print("  ⚠️  Restart daemon (opsi 8) biar perubahan kepakai.")
    _pause()


def _sched_set_times(cfg):
    from src import config_writer as cw
    _clear()
    if cfg.SCHEDULE_MODE == "interval":
        _header("🕐  Atur Interval")
        print(f"  Sekarang: tiap {cfg.INTERVAL_HOURS} jam, mulai {cfg.START_HOUR:02d}:00\n")
        ih = _prompt("Post tiap berapa jam? (1-24)", str(cfg.INTERVAL_HOURS))
        sh = _prompt("Mulai jam berapa? (0-23)", str(cfg.START_HOUR))
        try:
            ih_i = max(1, min(int(ih), 24))
            sh_i = int(sh) % 24
        except (ValueError, TypeError):
            print("  ❌ Input tidak valid (harus angka).")
            _pause()
            return
        cw.set_interval(ih_i, sh_i)
        # preview
        cfg2 = _reload_config_module()
        print(f"\n  ✅ Interval tiap {ih_i} jam dari {sh_i:02d}:00")
        print(f"  📅 Jam post jadi: {', '.join(cfg2.POST_TIMES)}")
    else:
        _header("🕐  Atur Jam Post (fixed)")
        print(f"  Sekarang: {', '.join(cfg.POST_TIMES)}\n")
        print("  Masukin jam dipisah koma, format HH:MM")
        print("  Contoh: 08:00, 13:00, 20:00\n")
        raw = _prompt("Jam post", ", ".join(cfg.POST_TIMES))
        times = []
        for part in (raw or "").split(","):
            t = part.strip()
            if not t:
                continue
            # validate HH:MM
            bits = t.split(":")
            if len(bits) != 2:
                print(f"  ❌ Format salah: '{t}' (harus HH:MM)")
                _pause()
                return
            try:
                hh, mm = int(bits[0]), int(bits[1])
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError
            except ValueError:
                print(f"  ❌ Jam tidak valid: '{t}'")
                _pause()
                return
            times.append(f"{hh:02d}:{mm:02d}")
        if not times:
            print("  ❌ Minimal 1 jam.")
            _pause()
            return
        # dedupe + sort
        times = sorted(set(times))
        cw.set_fixed_times(times)
        print(f"\n  ✅ Jam post: {', '.join(times)}")
    print("  ⚠️  Restart daemon (opsi 8) biar perubahan kepakai.")
    _pause()


def _sched_set_rest(cfg):
    from src import config_writer as cw
    _clear()
    _header("😴  Atur Rest Hours", "Jam daemon TIDAK posting")
    print(f"  Sekarang: {cfg.REST_START:02d}:00 – {cfg.REST_END:02d}:00\n")
    rs = _prompt("Rest mulai jam (0-23)", str(cfg.REST_START))
    re = _prompt("Rest selesai jam (0-23)", str(cfg.REST_END))
    try:
        rs_i = int(rs) % 24
        re_i = int(re) % 24
    except (ValueError, TypeError):
        print("  ❌ Input tidak valid.")
        _pause()
        return
    cw.set_rest_hours(rs_i, re_i)
    print(f"\n  ✅ Rest hours: {rs_i:02d}:00 – {re_i:02d}:00")
    print("  ⚠️  Restart daemon (opsi 8) biar perubahan kepakai.")
    _pause()


def _sched_set_autogen(cfg):
    from src import config_writer as cw
    _clear()
    _header("📦  Auto-Generate")
    print(f"  Sekarang: generate kalau stock < {cfg.STOCK_MIN}, batch {cfg.BATCH_SIZE}\n")
    sm = _prompt("Stock minimum (trigger generate)", str(cfg.STOCK_MIN))
    bs = _prompt("Batch size (berapa story sekali generate)", str(cfg.BATCH_SIZE))
    try:
        sm_i = max(0, int(sm))
        bs_i = max(1, int(bs))
    except (ValueError, TypeError):
        print("  ❌ Input tidak valid.")
        _pause()
        return
    cw.set_auto_generate(sm_i, bs_i)
    print(f"\n  ✅ Auto-gen: stock < {sm_i}, batch {bs_i}")
    print("  ⚠️  Restart daemon (opsi 8) biar perubahan kepakai.")
    _pause()


def _sched_set_tz(cfg):
    from src import config_writer as cw
    _clear()
    _header("🌏  Timezone")
    print(f"  Sekarang: {cfg.TIMEZONE}\n")
    print("  Contoh: Asia/Jakarta, Asia/Makassar, UTC\n")
    tzname = _prompt("Timezone (IANA)", cfg.TIMEZONE)
    if not tzname:
        return
    # validate tz
    try:
        from dateutil import tz as _tz
        if _tz.gettz(tzname) is None:
            print(f"  ❌ Timezone '{tzname}' tidak dikenali.")
            _pause()
            return
    except Exception:
        pass
    cw.set_timezone(tzname)
    print(f"\n  ✅ Timezone: {tzname}")
    print("  ⚠️  Restart daemon (opsi 8) biar perubahan kepakai.")
    _pause()


def _sched_install_unit():
    _clear()
    _header("🔧  Install / Perbaiki Service", "Auto-detect path checkout ini")
    import os, sys
    print(f"  Project dir : {BASE_DIR}")
    print(f"  Python      : {sys.executable if not os.path.exists(os.path.join(BASE_DIR,'venv','bin','python3')) else os.path.join(BASE_DIR,'venv','bin','python3')}")
    print(f"  User        : {os.environ.get('USER') or os.environ.get('LOGNAME') or 'root'}")
    print(f"  Unit file   : {_unit_path()}")
    needs, reason = _unit_needs_install()
    print(f"  Status      : {'⚠️ ' + reason if needs else '✅ sudah benar'}")
    print()
    print("  Unit yang akan dipasang:")
    print("  " + "─" * 48)
    for line in _expected_unit_text().splitlines():
        print(f"    {line}")
    print("  " + "─" * 48)
    ans = _prompt("Pasang/perbaiki sekarang? (y/n)", "y")
    if (ans or "").strip().lower() not in ("y", "yes", ""):
        print("  Dibatalkan.")
        _pause()
        return
    ok, out = _install_unit()
    if ok:
        print(f"\n  ✅ {out}")
        print("  ▶️  Sekarang bisa Start daemon (opsi 6).")
    else:
        print(f"\n  ❌ {out}")
    _pause()


def _sched_daemon_start():
    _clear()
    _header("▶️  Start Daemon")
    # auto-install/repair the unit for THIS checkout if missing or path-mismatched
    needs, reason = _unit_needs_install()
    if needs:
        print(f"  🔧 Service perlu dipasang/diperbaiki: {reason}")
        ok_i, out_i = _install_unit()
        if ok_i:
            print(f"  ✅ {out_i}")
        else:
            print(f"  ❌ {out_i}")
            _pause()
            return
    active, enabled = _daemon_status()
    if active == "active":
        print("  ℹ️  Daemon sudah RUNNING.")
        _pause()
        return
    print(f"  Service: {SYSTEMD_SERVICE}")
    print("  Daemon ini persistent — tetap jalan walau SSH/VPS lo tutup,")
    print("  dan auto-restart kalau crash atau VPS reboot.\n")
    # enable for boot persistence + start now
    ok_en, out_en = _systemctl("enable")
    ok, out = _systemctl("start")
    if ok:
        print("  ✅ Daemon STARTED + enabled (auto-start saat boot).")
        print("  📜 Cek log: opsi 9")
    else:
        print(f"  ❌ Gagal start: {out}")
        print("  💡 Mungkin perlu sudo. Coba manual:")
        print(f"     sudo systemctl enable --now {SYSTEMD_SERVICE}")
    _pause()


def _sched_daemon_stop():
    _clear()
    _header("⏹️  Stop Daemon")
    ok, out = _systemctl("stop")
    if ok:
        print("  ✅ Daemon STOPPED.")
        print("  ℹ️  Masih auto-start saat boot. Buat matiin permanen:")
        print(f"     sudo systemctl disable {SYSTEMD_SERVICE}")
    else:
        print(f"  ❌ Gagal stop: {out}")
        print(f"  💡 Coba: sudo systemctl stop {SYSTEMD_SERVICE}")
    _pause()


def _sched_daemon_restart():
    _clear()
    _header("🔄  Restart Daemon", "Apply config baru")
    # auto-repair unit if it points at the wrong path (e.g. cloned to new dir)
    needs, reason = _unit_needs_install()
    if needs:
        print(f"  🔧 Service perlu diperbaiki dulu: {reason}")
        ok_i, out_i = _install_unit()
        if ok_i:
            print(f"  ✅ {out_i}")
        else:
            print(f"  ❌ {out_i}")
            _pause()
            return
    ok, out = _systemctl("restart")
    if ok:
        print("  ✅ Daemon RESTARTED — config baru kepakai.")
    else:
        print(f"  ❌ Gagal restart: {out}")
        print(f"  💡 Coba: sudo systemctl restart {SYSTEMD_SERVICE}")
    _pause()


def _sched_daemon_logs():
    _clear()
    _header("📜  Log Daemon (live)", "Ctrl+C untuk kembali")
    import os, subprocess
    # Prefer the app's own log file (no privilege needed); fall back to journalctl.
    log_file = os.path.join(BASE_DIR, "logs", "systemd.log")
    if not os.path.exists(log_file):
        alt = os.path.join(BASE_DIR, "logs", "pipeline.log")
        log_file = alt if os.path.exists(alt) else None

    try:
        if log_file:
            print(f"  Tailing {log_file} (Ctrl+C untuk stop)\n")
            subprocess.run(["tail", "-n", "50", "-f", log_file], timeout=None)
        else:
            print("  Streaming journalctl... (Ctrl+C untuk stop)\n")
            cmd = ["journalctl", "-u", SYSTEMD_SERVICE, "-n", "50", "-f"]
            if _need_sudo():
                cmd = ["sudo", "-n"] + cmd
            subprocess.run(cmd, timeout=None)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"  ❌ Gagal baca log: {e}")
        print(f"  💡 Coba manual: tail -f {os.path.join(BASE_DIR, 'logs', 'systemd.log')}")
        print(f"     atau: journalctl -u {SYSTEMD_SERVICE} -f")
        _pause()


def menu_system():
    while True:
        _clear()
        _header("🔧  System & Tools")

        print("  1) 🗄️  Init Database")
        print("  2) 📢  Test Telegram Notifikasi")
        print("  3) 🌐  Start Dashboard (http://IP:8080)")
        print("  4) ⏰  Scheduler (pengaturan + start/stop daemon)")
        print("  5) 📖  CLI Reference")
        print("  6) 📊  Export CSV")
        print()
        print("  0) ← Kembali")

        ch = _prompt("Pilih")

        if ch in (None, "0"):
            break
        elif ch == "1":
            from src import database as db
            db.init_db()
            print("  ✅ Database siap.")
            _pause()
        elif ch == "2":
            from src import notifier as tg, database as db
            db.init_db()
            from src.config import config
            ok = tg.notify_startup(config.POST_TIMES, db.count_stories("story_ready"))
            print("  ✅ Telegram terkirim!" if ok else "  ❌ Gagal. Cek TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID")
            _pause()
        elif ch == "3":
            print("\n  🌐 Starting dashboard di http://0.0.0.0:8080 ...")
            print("  (Ctrl+C untuk stop)")
            from src.dashboard import serve
            serve()
        elif ch == "4":
            menu_scheduler()
        elif ch == "5":
            _show_cli_ref()
        elif ch == "6":
            _system_export_csv()


def _system_export_csv():
    import csv
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, topic, title, status, source_url, LENGTH(story_body) as chars FROM articles ORDER BY id")
    rows = c.fetchall()
    conn.close()

    out = os.path.join(BASE_DIR, "data", "export_articles.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "topic", "title", "status", "source_url", "chars"])
        for r in rows:
            w.writerow([r["id"], r["topic"], r["title"] or "", r["status"], r["source_url"] or "", r["chars"] or 0])

    print(f"  ✅ Exported {len(rows)} artikel ke {out}")
    _pause()


def _show_cli_ref():
    _clear()
    _header("📖  CLI Reference")

    print("  ── Interactive Menu ──")
    print("  python3 run.py menu              # Menu interaktif")
    print()
    print("  ── Quick Commands ──")
    print("  python3 run.py status            # Status pipeline")
    print("  python3 run.py add \"Topik\"       # Scrape + generate")
    print("  python3 run.py publish [id]      # Publish ke FB")
    print("  python3 run.py publish-all [n]   # Batch publish")
    print("  python3 run.py list              # Lihat semua artikel")
    print("  python3 run.py story <id>        # Generate story")
    print("  python3 run.py scrape \"Topik\"    # Scrape saja")
    print("  python3 run.py show <id>         # Lihat story")
    print("  python3 run.py categories        # Daftar kategori")
    print("  python3 run.py random <kat>      # Random 1 topik")
    print("  python3 run.py batch <kat> [n]   # Random N topik")
    print("  python3 run.py luck [n]          # Random semua")
    print()
    print("  ── Daemon ──")
    print("  python3 main.py run              # Scheduler daemon")
    print("  python3 main.py status           # Status")
    print("  python3 main.py test-post        # Test publish")
    print("  python3 main.py test-notif       # Test Telegram")
    print("  python3 main.py generate [n]     # Generate stories")
    print()
    print("  ── Systemd ──")
    print("  systemctl start hive             # Start daemon")
    print("  systemctl stop hive              # Stop daemon")
    print("  systemctl status hive            # Cek status")
    print("  journalctl -u hive -f            # Live logs")

    _pause()
