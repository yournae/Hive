import json, logging, re, os
from . import database as db, scraper, storyteller, publisher
from .config import config
log = logging.getLogger("pipeline")

def _slugify(text):
    """Ubah judul topik jadi filename aman."""
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '_', s)
    return s[:80] or 'untitled'

def _save_scraped_file(topic, scraped_data):
    """Simpan hasil scrape ke data/scraped/{slug}.json"""
    slug = _slugify(topic)
    path = os.path.join(config.SCRAPED_DIR, f"{slug}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, ensure_ascii=False, indent=2)
    log.info("Scraped file tersimpan: %s", path)
    return path

def _save_story_file(topic, story_title, story_body):
    """Simpan story ke data/stories/{slug}.txt"""
    slug = _slugify(topic)
    path = os.path.join(config.STORIES_DIR, f"{slug}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"JUDUL: {story_title}\n")
        f.write("---\n")
        f.write(story_body)
    log.info("Story file tersimpan: %s", path)
    return path

def ingest(topic, url=None):
    db.init_db()
    os.makedirs(config.SCRAPED_DIR, exist_ok=True)
    os.makedirs(config.STORIES_DIR, exist_ok=True)
    s = scraper.scrape(topic, url)
    result = db.add_article(topic, s["source_url"], s["title"], s)
    # result is always dict with "id" and "is_new"
    aid = result["id"]
    if not result["is_new"]:
        existing = db.get_article(aid)
        if existing and existing.get("story_title"):
            log.info("Story sudah ada id=%s: %s", aid, existing["story_title"])
            return {"id": aid, "status": "has_story"}
        log.info("Artikel sudah di-scrape id=%s, lanjut bikin story...", aid)
        _save_scraped_file(topic, s)
        return {"id": aid, "status": "existing"}
    _save_scraped_file(topic, s)
    log.info("Scraped id=%s: %s", aid, s["title"])
    return {"id": aid, "status": "new"}

def make_story(aid):
    a = db.get_article(aid)
    if not a: raise ValueError("Article tidak ada: %s" % aid)
    if not a.get("scraped_json"):
        raise ValueError("Article id=%s has no scraped_json data" % aid)
    story = storyteller.generate_story(json.loads(a["scraped_json"]))
    db.save_story(aid, story["title"], story["body"])
    # Simpan file story
    _save_story_file(a["topic"], story["title"], story["body"])
    log.info("Story dibuat id=%s", aid); return story

def add(topic, url=None):
    r = ingest(topic, url)
    if r["status"] == "has_story":
        return None
    make_story(r["id"]); return r["id"]

def publish_next():
    db.init_db()
    a = db.get_next_unposted()
    if not a: log.info("Tidak ada artikel siap posting."); return None
    return _do_publish(a)

def publish_by_id(aid):
    db.init_db()
    a = db.get_article(aid)
    if not a: raise ValueError("Article tidak ada: %s" % aid)
    if a["status"] == "posted": log.info("Sudah di-post id=%s fb=%s", aid, a.get("fb_post_id")); return None
    if not a.get("story_body"): raise ValueError("Belum ada story untuk id=%s. Jalankan: python run.py story %s" % (aid, aid))
    return _do_publish(a)

def _do_publish(a):
    msg = (a["story_title"] + "\n\n" + a["story_body"]) if a["story_title"] else a["story_body"]
    title = a.get("story_title") or a.get("topic", "?")
    body = a.get("story_body", "") or ""
    try:
        publisher.validate_token()
        pid, url = publisher.publish_post(msg)
        db.mark_posted(a["id"], pid, url)
        log.info("Posted id=%s fb=%s", a["id"], pid)
        # Notif sukses — chokepoint tunggal, jalan untuk manual & scheduler.
        try:
            from . import notifier as tg
            tg.notify_published(title, len(body), url)
        except Exception as ne:
            log.warning("Notif published gagal id=%s: %s", a["id"], ne)
        return {"post_id": pid, "post_url": url}
    except publisher.TokenError as e:
        db.log_failure(a["id"], "TOKEN: " + str(e)); log.error("Token error: %s", e)
        try:
            from . import notifier as tg
            tg.notify_error(str(e)[:300], f"publish id={a['id']} (token)")
        except Exception as ne:
            log.warning("Notif error gagal id=%s: %s", a["id"], ne)
        raise
    except Exception as e:
        db.log_failure(a["id"], str(e)); log.error("Publish gagal: %s", e)
        try:
            from . import notifier as tg
            tg.notify_error(str(e)[:300], f"publish id={a['id']}")
        except Exception as ne:
            log.warning("Notif error gagal id=%s: %s", a["id"], ne)
        raise
