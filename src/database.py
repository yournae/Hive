import sqlite3, json, hashlib, datetime, os
from .config import config

def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = _conn(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS articles(
        id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT,
        source_url TEXT UNIQUE, title TEXT, content_hash TEXT UNIQUE,
        scraped_json TEXT, story_title TEXT, story_body TEXT,
        status TEXT DEFAULT 'scraped', created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER,
        fb_post_id TEXT, post_url TEXT, status TEXT, error_message TEXT,
        posted_at TEXT, FOREIGN KEY(article_id) REFERENCES articles(id))''')
    try:
        conn.commit()
    finally:
        conn.close()

def _hash(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

def article_exists(source_url=None, chash=None):
    conn = _conn(); c = conn.cursor()
    if source_url:
        c.execute("SELECT * FROM articles WHERE source_url=?", (source_url,))
        r = c.fetchone()
        if r: conn.close(); return dict(r)
    if chash:
        c.execute("SELECT * FROM articles WHERE content_hash=?", (chash,))
        r = c.fetchone()
        if r: conn.close(); return dict(r)
    conn.close(); return None

def add_article(topic, source_url, title, scraped):
    # PENTING: hash dihitung dari konten yang STABIL saja (tanpa last_accessed).
    # Kalau last_accessed (timestamp) ikut di-hash, hash selalu beda tiap scrape
    # walau isinya identik -> dedup by content_hash jadi gak pernah kena.
    raw = json.dumps(scraped, ensure_ascii=False)
    stable = {k: v for k, v in scraped.items() if k != "last_accessed"}
    ch = _hash(json.dumps(stable, ensure_ascii=False, sort_keys=True))
    existing = article_exists(source_url, ch)
    if isinstance(existing, dict):
        return {"id": existing["id"], "is_new": False}
    conn = _conn(); c = conn.cursor()
    c.execute('''INSERT INTO articles(topic,source_url,title,content_hash,scraped_json,status,created_at)
                 VALUES(?,?,?,?,?,?,?)''',
              (topic, source_url, title, ch, raw, 'scraped',
               datetime.datetime.utcnow().isoformat()))
    conn.commit(); aid = c.lastrowid; conn.close()
    return {"id": aid, "is_new": True}

def save_story(aid, t, b):
    conn = _conn(); c = conn.cursor()
    c.execute("UPDATE articles SET story_title=?,story_body=?,status='story_ready' WHERE id=?", (t, b, aid))
    conn.commit(); conn.close()

def get_article(aid):
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE id=?", (aid,)); r = c.fetchone(); conn.close()
    return dict(r) if r else None

def get_next_unposted():
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE status='story_ready' ORDER BY created_at ASC LIMIT 1")
    r = c.fetchone(); conn.close(); return dict(r) if r else None

def mark_posted(aid, fb_id, url):
    conn = _conn(); c = conn.cursor()
    c.execute("UPDATE articles SET status='posted' WHERE id=?", (aid,))
    c.execute('''INSERT INTO posts(article_id,fb_post_id,post_url,status,posted_at)
                 VALUES(?,?,?,?,?)''', (aid, fb_id, url, 'success',
                 datetime.datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def log_failure(aid, msg):
    conn = _conn(); c = conn.cursor()
    c.execute("UPDATE articles SET status='failed' WHERE id=?", (aid,))
    c.execute('''INSERT INTO posts(article_id,status,error_message,posted_at)
                 VALUES(?,?,?,?)''', (aid, 'failed', msg,
                 datetime.datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def get_stats():
    conn = _conn(); c = conn.cursor(); s = {}
    c.execute("SELECT COUNT(*) FROM articles"); s['total_articles'] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM articles WHERE status='story_ready'"); s['ready'] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM articles WHERE status='posted'"); s['posted'] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM articles WHERE status='failed'"); s['failed'] = c.fetchone()[0]
    conn.close(); return s

def get_recent_posts(limit=20):
    conn = _conn(); c = conn.cursor()
    c.execute('''SELECT p.*, a.title FROM posts p LEFT JOIN articles a ON p.article_id=a.id
                 ORDER BY p.posted_at DESC LIMIT ?''', (limit,))
    rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows


def count_stories(status: str) -> int:
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM articles WHERE status=?", (status,))
    count = c.fetchone()[0]
    conn.close(); return count


def count_posted_today() -> int:
    """Jumlah post sukses 'hari ini' (zona waktu config.TIMEZONE).

    posted_at disimpan UTC ISO. Kita konversi batas hari lokal → UTC lalu hitung.
    Aman dipanggil dari manual maupun scheduler (sumber kebenaran = DB).
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(getattr(config, "TIMEZONE", "Asia/Jakarta"))
    except Exception:
        tz = None
    now_local = datetime.datetime.now(tz) if tz else datetime.datetime.utcnow()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    if tz:
        start_utc = start_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    else:
        start_utc = start_local
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM posts WHERE status='success' AND posted_at >= ?",
              (start_utc.isoformat(),))
    count = c.fetchone()[0]
    conn.close(); return count


def delete_article(aid: int) -> bool:
    """Delete article and its posts from DB. Returns True if deleted."""
    import sqlite3
    from .config import config
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM posts WHERE article_id=?", (aid,))
    c.execute("DELETE FROM articles WHERE id=?", (aid,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_articles_by_status(status: str, limit: int = 50) -> list:
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE status=? ORDER BY created_at ASC LIMIT ?", (status, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close(); return rows


def get_next_pending() -> dict | None:
    """Get next article ready to publish (story_ready)."""
    return get_next_unposted()
