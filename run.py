import sys, logging
from src import pipeline, database, topic_selector
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def usage():
    print("""╔═══════════════════════════════════════════════╗
║        HIVE — CLI TOOLKIT                  ║
╚═══════════════════════════════════════════════╝

Usage:
  python3 run.py menu                             # interactive menu (recommended!)
  python3 run.py status                           # pipeline status
  python3 run.py initdb                           # init database
  python3 run.py categories                      # list kategori + jumlah topik

  # ── TOPIC RANDOMIZER ──
  python3 run.py random <category_id>            # 1 topik random, weighted by engagement
  python3 run.py batch <category_id> [n=3]       # N topik random tanpa duplikat
  python3 run.py luck [n=1]                      # dari SEMUA kategori

  # ── SCRAPE + STORY ──
  python3 run.py add "Topik" [--url URL]         # scrape + storytelling (siap posting)
  python3 run.py scrape "Topik" [--url URL]      # scrape saja
  python3 run.py story <article_id>              # buat storytelling dari artikel
  python3 run.py show <article_id>               # tampilkan hasil story

  # ── BROWSE ──
  python3 run.py list                            # list semua artikel + ID + status

  # ── PUBLISH ──
  python3 run.py publish [id]                    # tanpa id: next dari queue; dengan id: posting topik tertentu
  python3 run.py publish-all [n=5]               # batch posting n artikel

  # ── SERVER ──
  python3 run.py serve                           # dashboard (http://IP:8080)
  python3 run.py schedule                        # scheduler 24/7 (09:00 & 19:00)""")
    print()
    print_categories()

def print_categories():
    cats = topic_selector.list_categories()
    print("Categories:")
    for c in cats:
        print(f"  {c['id']:<17} — {c['description']:40s} ({c['count']} topik)")

def main():
    if len(sys.argv) < 2:
        return usage()

    cmd = sys.argv[1]
    url = None
    if "--url" in sys.argv:
        idx = sys.argv.index("--url")
        url = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    # ── HELP ──
    if cmd in ("-h", "--help", "help"):
        return usage()

    # ── MENU ──
    if cmd in ("menu", "m"):
        from src.cli_menu import main_menu
        main_menu()
        return

    # ── SYSTEM ──
    if cmd == "status":
        from src.config import config as cfg
        database.init_db()
        s = database.get_stats()
        print("╔══════════════════════════════════════════════╗")
        print("║        🐝  HIVE — STATUS  🐝              ║")
        print("╚══════════════════════════════════════════════╝")
        print(f"  ⏰  Schedule: {', '.join(cfg.POST_TIMES)} WIB")
        print(f"  📦  Story Ready: {s['ready']}")
        print(f"  ✅  Posted: {s['posted']}")
        print(f"  ❌  Failed: {s['failed']}")
        print(f"  📊  Total: {s['total_articles']} articles")
        print()
        return

    if cmd == "initdb":
        database.init_db()
        print("DB siap.")
        return

    elif cmd in ("categories", "category", "cat"):
        cats = topic_selector.list_categories()
        print(f"{'Kategori':<20} {'Topik':<5} Deskripsi")
        print("-" * 60)
        for c in cats:
            print(f"{c['id']:<20} {c['count']:<5} {c['description']}")

    # ── TOPIC SELECTOR ──
    elif cmd == "random":
        if len(sys.argv) < 3:
            print("Usage: python run.py random <category_id>")
            print("Kategori: misteri, sejarah_gelap, tokoh, bencana, fenomena_alam, budaya_unik")
            return
        t = topic_selector.random_topic(sys.argv[2])
        print(f"\n🧵 {t['category']}")
        print(f"═══ {'═' * len(t['category'])}")
        print(f"  Topik:          {t['topic']}")
        print(f"  Engagement:     {'⭐' * t['engagement_score']} ({t['engagement_score']}/10)")
        print(f"  Tags:           {', '.join(t['tags'])}")
        if t["notes"]:
            print(f"  Notes:          {t['notes']}")
        print()

    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("Usage: python run.py batch <category_id> [n=3]")
            return
        try:
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        except ValueError:
            print(f"Error: '{sys.argv[3]}' bukan angka"); return
        batch = topic_selector.random_batch(sys.argv[2], n)
        print(f"\n{len(batch['topics'])} Topik dari: {batch['category']}")
        print(f"═══ {'═' * (len(batch['category']) + 5)}")
        for i, t in enumerate(batch["topics"], 1):
            print(f"\n  {i}. {t['topic']}")
            print(f"     {'⭐' * t['engagement_score']} ({t['engagement_score']}/10)")
            if t["notes"]:
                print(f"     {t['notes']}")
        print()

    elif cmd == "luck":
        try:
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        except ValueError:
            print(f"Error: '{sys.argv[2]}' bukan angka"); return
        topics = topic_selector.random_from_all(n)
        print(f"\n🎲 Random dari SEMUA kategori ({n} topik)")
        print("═══ ═══════════════════════════")
        for i, t in enumerate(topics, 1):
            print(f"\n  {i}. [{t['category']}] {t['topic']}")
            print(f"     {'⭐' * t['engagement_score']} ({t['engagement_score']}/10)")
            if t["notes"]:
                print(f"     {t['notes']}")
        print()

    # ── SCRAPE + STORY ──
    elif cmd == "scrape":
        if len(sys.argv) < 3:
            print('Error: butuh argumen topik. Contoh: python run.py scrape "Topik"')
            return
        result = pipeline.ingest(sys.argv[2], url)
        aid = result.get("id") if result else None
        print("article_id:", aid)

    elif cmd == "add":
        if len(sys.argv) < 3:
            print('Error: butuh argumen topik. Contoh: python run.py add "Topik"')
            return
        print("article_id:", pipeline.add(sys.argv[2], url))

    elif cmd == "story":
        if len(sys.argv) < 3:
            print("Error: butuh article_id. Contoh: python run.py story 1")
            return
        s = pipeline.make_story(int(sys.argv[2]))
        print(s["title"])
        print("---")
        print(s["body"])

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Error: butuh article_id. Contoh: python run.py show 1")
            return
        a = database.get_article(int(sys.argv[2]))
        if not a:
            print("Article id tidak ditemukan.")
            return
        print(a["story_title"])
        print("---")
        print(a["story_body"])

    # ── PUBLISH ──
    elif cmd in ("list", "ls", "articles"):
        import sqlite3
        from src.config import config
        db = sqlite3.connect(config.DB_PATH)
        db.row_factory = sqlite3.Row
        cur = db.execute("SELECT id, topic, title, status, story_title, LENGTH(story_body) as len FROM articles ORDER BY id")
        rows = cur.fetchall()
        if not rows:
            print("Belum ada artikel. Jalankan: python run.py add \"Topik\"")
            return
        print(f"{'ID':>3} {'Status':<14} {'Chars':>8} {'Topik':<30} {'Judul Story'}")
        print("─" * 100)
        for r in rows:
            st = r["status"]
            icon = "✅" if st == "posted" else "❌" if st == "failed" else "📝" if st == "scraped" else "📖"
            title = r["story_title"] or "—"
            chars = f"{r['len']:>7,}" if r["len"] else "      —"
            print(f"{r['id']:>3} {icon} {st:<12} {chars} {r['topic']:<30} {title[:40]}")
        db.close()
        print(f"\nTotal: {len(rows)} artikel")

    elif cmd == "publish":
        if len(sys.argv) > 2:
            # python run.py publish <id>
            aid = int(sys.argv[2])
            result = pipeline.publish_by_id(aid)
            if result:
                print(f"✅ Posted id={aid} → {result['post_url']}")
            else:
                print(f"⚠️  id={aid} sudah pernah di-post atau gak ada.")
        else:
            # python run.py publish (next from queue)
            result = pipeline.publish_next()
            if result:
                print(f"✅ Posted → {result['post_url']}")
            else:
                print("⚠️  Antrian kosong.")

    elif cmd == "publish-all":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        for _ in range(n):
            result = pipeline.publish_next()
            if result:
                print(f"✅ Posted: {result['post_id']}")
            else:
                print("⚠️  Antrian kosong.")
                break

    # ── SERVER ──
    elif cmd == "serve":
        from src.dashboard import serve
        serve()

    elif cmd == "schedule":
        from src.scheduler import PublisherScheduler
        from src import database as db
        db.init_db()
        s = PublisherScheduler()
        s.run()

    else:
        usage()

if __name__ == "__main__":
    main()
