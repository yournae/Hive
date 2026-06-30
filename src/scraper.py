import requests, datetime, time, logging, re
from urllib.parse import unquote, quote
from bs4 import BeautifulSoup
from .config import config

log = logging.getLogger(__name__)

API = "https://{lang}.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# curl_cffi bypasses WAF/Cloudflare when available
try:
    from curl_cffi import requests as cf_requests
    _cf_get = lambda url, **kw: cf_requests.get(url, impersonate="chrome", **kw)
    # curl_cffi melempar exception class SENDIRI yang BUKAN subclass dari
    # requests.exceptions.RequestException — kalau ga ditangkap, retry-loop
    # ke-bypass dan crash mentah di environment tempat curl_cffi aktif.
    try:
        from curl_cffi.requests.exceptions import RequestException as _CfError
    except ImportError:
        try:
            from curl_cffi.requests import RequestsError as _CfError
        except ImportError:
            from curl_cffi import CurlError as _CfError
except ImportError:
    _cf_get = None
    _CfError = None

# Tuple exception yang dianggap "network error layak retry"
_NET_ERRORS = tuple(
    e for e in (requests.exceptions.RequestException, _CfError) if e is not None
)

# Prefix yg sering ada di topic bank tapi tidak ada di judul Wikipedia.
# Urutan penting: prefix panjang dulu, baru pendek.
_CLEAN_PREFIXES = [
    "Hantu Kapal ", "hantu kapal ",
    "Kapal Hantu ", "kapal hantu ",
    "Cerita Misteri ", "cerita misteri ",
    "Dunia Misterius ", "dunia misterius ",
    "Kisah Misteri ", "kisah misteri ",
    "Fakta Menarik ", "fakta menarik ",
    "Urban Legend ", "urban legend ",
    "Kisah Misterius ", "kisah misterius ",
    "Misteri ", "misteri ",
    "Hantu ", "hantu ",
    "Legenda ", "legenda ",
    "Kisah ", "kisah ",
    "Cerita ", "cerita ",
    "Tragedi ", "tragedi ",
    "Sejarah ", "sejarah ",
    "Fenomena ", "fenomena ",
    "Mitos ", "mitos ",
    "Konspirasi ", "konspirasi ",
    "Misterius ", "misterius ",
    "Peristiwa ", "peristiwa ",
    "Kasus ", "kasus ",
    "Kejadian ", "kejadian ",
    "Rahasia ", "rahasia ",
    "Kontroversi ", "kontroversi ",
    "Fakta ", "fakta ",
    "Asal Usul ", "asal usul ",
    "Bencana ", "bencana ",
    "Ledakan ", "ledakan ",
    "Pembantaian ", "pembantaian ",
    "Penculikan ", "penculikan ",
    "Klaim ", "klaim ",
    "Ritual ", "ritual ",
    "Teori ", "teori ",
    "Penemuan ", "penemuan ",
    "Kepunahan ", "kepunahan ",
    "Kehidupan ", "kehidupan ",
    "Kematian ", "kematian ",
    "Pembunuhan ", "pembunuhan ",
    "Biografi ", "biografi ",
    "Profil ", "profil ",
    "Seram ", "seram ",
    "Horor ", "horor ",
]


def _api(lang):
    return API.format(lang=lang)


def _clean_topic_name(topic):
    """Hapus prefix umum yang tidak ada di Wikipedia. Hanya strip sekali."""
    for prefix in _CLEAN_PREFIXES:
        if topic.startswith(prefix) and len(topic) > len(prefix) + 3:
            return topic[len(prefix):]
    return topic


def _request_with_retry(url, params=None, max_retries=5, timeout=30):
    """HTTP GET with exponential backoff. Uses curl_cffi if available (bypasses WAF)."""
    _get = _cf_get or requests.get

    r = None
    for attempt in range(max_retries):
        try:
            r = _get(url, params=params, timeout=timeout)
            if r.status_code in (403, 429):
                wait = min(2 ** attempt * 5, 60)
                log.warning("HTTP %d, waiting %ds (attempt %d/%d)", r.status_code, wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                wait = min(2 ** attempt * 2, 30)
                log.warning("HTTP %d, waiting %ds (attempt %d/%d)", r.status_code, wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            return r
        except _NET_ERRORS as e:
            if attempt < max_retries - 1:
                wait = min(2 ** attempt * 3, 30)
                log.warning("Request error: %s, retrying in %ds", e, wait)
                time.sleep(wait)
            else:
                raise
    log.warning("All %d retries exhausted (last status: %s)", max_retries, r.status_code if r else "N/A")
    return r  # return last response, caller handles


def _try_parse_page(topic, lang):
    """Try to get a page via parse API. Returns title or None."""
    r = _request_with_retry(_api(lang), params={
        "action": "parse", "page": topic,
        "format": "json", "redirects": 1
    })
    if r and r.status_code == 200:
        try:
            data = r.json()
            if "parse" in data:
                return data["parse"].get("title", topic)
        except Exception:
            pass
    return None


def _search_page_api(topic, lang):
    """Search via Wikipedia search API. Returns best matching title or None."""
    r = _request_with_retry(_api(lang), params={
        "action": "query", "list": "search",
        "srsearch": topic, "format": "json", "srlimit": 15
    })
    if not r or r.status_code != 200:
        return None
    results = r.json().get("query", {}).get("search", [])
    if not results:
        return None

    from difflib import SequenceMatcher
    best_title = None
    best_score = 0
    topic_lower = topic.lower()
    topic_words = [w for w in topic_lower.split() if len(w) > 2]

    for item in results:
        title = item["title"]
        title_lower = title.lower()

        # Skor utama: similarity dengan full query
        r1 = SequenceMatcher(None, topic_lower, title_lower).ratio()

        # Skor alternatif: similarity dengan cleaned name
        cleaned = _clean_topic_name(topic)
        r2 = SequenceMatcher(None, cleaned.lower(), title_lower).ratio()

        # Skor keyword: cocokkan dengan setiap kata individu di query
        max_word_sim = 0
        for word in topic_words:
            ws = SequenceMatcher(None, word.lower(), title_lower).ratio()
            if ws > max_word_sim:
                max_word_sim = ws

        score = max(r1, r2, max_word_sim)

        # Bonus: exact word-boundary match (title contains word as standalone term)
        for word in topic_words:
            if len(word) >= 4 and re.search(r'\b' + re.escape(word) + r'\b', title_lower):
                score = max(score, 0.60)
                break

        if score > best_score:
            best_score = score
            best_title = title

    # Threshold adaptif: topic lebih pendek → lebih strict, topic lebih panjang → lebih longgar
    word_count = len(topic.split())
    if word_count >= 4:
        threshold = 0.45  # "Fenomena Haboob Sand Storm" (4w) → "Haboob" score 0.52 ✅
    elif word_count >= 3:
        threshold = 0.50  # "Haboob Sand Storm" (3w) → "Haboob" 0.52 ✅; "Von Neumann Probes" → "Kromosom" 0.43 ❌
    else:
        threshold = 0.55

    if best_score >= threshold:
        log.debug("Search match: '%s' → '%s' (score=%.2f, threshold=%.2f)", topic, best_title, best_score, threshold)
        return best_title
    else:
        log.debug("No good match for '%s': best='%s' (score=%.2f < %.2f)", topic, best_title, best_score, threshold)
    return None


def _search_variations(topic):
    """Generate multiple search term variations for a topic.

    Contoh: 'Fenomena Haboob Sand Storm' → [
        'Fenomena Haboob Sand Storm', 'Haboob Sand Storm',
        'Haboob', 'Storm', 'Fenomena'
    ]

    Contoh: 'Peristiwa Malari 1974' → [
        'Peristiwa Malari 1974', 'Malari 1974',
        'Peristiwa Malari', 'Malari',
    ]
    """
    seen = set()
    variations = []

    def add(t):
        t = t.strip()
        if t and len(t) > 2 and t.lower() not in seen:
            seen.add(t.lower())
            variations.append(t)

    # 1. Original
    add(topic)

    # 2. Stripped prefix
    cleaned = _clean_topic_name(topic)
    if cleaned != topic:
        add(cleaned)

    # 3. Stripped trailing year (4 digit di akhir)
    no_year = re.sub(r'\s*\d{4}\s*$', '', topic).strip()
    if no_year != topic and len(no_year) > 3:
        add(no_year)

    no_year_clean = re.sub(r'\s*\d{4}\s*$', '', cleaned).strip()
    if no_year_clean != cleaned and len(no_year_clean) > 3 and no_year_clean != no_year:
        add(no_year_clean)

    # 4. Compound: first + last word (utk kasus 3+ kata)
    words = cleaned.split()
    if len(words) >= 3:
        compound = f"{words[0]} {words[-1]}"
        if len(compound) > 4:
            add(compound)

    return variations


def search_page(topic, lang):
    """Find Wikipedia page for a topic.

    Strategy:
    1. Generate multiple search term variations (prefix-stripped, year-stripped, key words)
    2. Try exact parse for each variation
    3. Try Wikipedia search API for each variation (with adaptive similarity threshold)
    """
    variations = _search_variations(topic)
    log.debug("Search variations for '%s' [%s]: %s", topic, lang, variations)

    # Phase 1: Try exact parse for each variation (cepat, akurat)
    for v in variations:
        title = _try_parse_page(v, lang)
        if title:
            log.debug("Parse match: '%s' → '%s'", v, title)
            return title

    # Phase 2: Search API for each variation (lebih lambat, tapi dapet yg mirip)
    for v in variations:
        title = _search_page_api(v, lang)
        if title:
            log.debug("Search match via variation: '%s' → '%s'", v, title)
            return title

    return None


def _web_search_fallback(topic):
    """Cari halaman Wikipedia via DuckDuckGo search.

    Digunakan sebagai fallback terakhir ketika Wikipedia search API gagal.
    """
    try:
        r = _request_with_retry("https://html.duckduckgo.com/html/", params={
            "q": f"{topic} site:en.wikipedia.org"
        }, timeout=15)
        if not r or r.status_code != 200:
            return None, None
        soup = BeautifulSoup(r.text, "lxml")

        # Cari semua link yg mengarah ke en.wikipedia.org
        for a in soup.select("a[href*='en.wikipedia.org']"):
            href = a.get("href", "")
            # DuckDuckGo wrapping URL: /l/?uddg=... atau direct
            if "uddg=" in href:
                from urllib.parse import parse_qs, urlparse
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                href = qs.get("uddg", [""])[0]
            if "/wiki/" in href:
                title = unquote(href.split("/wiki/")[-1]).replace("_", " ").split("#")[0]
                if title:
                    log.debug("Web search fallback: '%s' → '%s'", topic, title)
                    return title, "en"
    except Exception as e:
        log.warning("Web search fallback gagal: %s", e)

    return None, None


def _title_from_url(u):
    return unquote(u.rstrip("/").split("/wiki/")[-1]).replace("_", " ")


def _lang_from_url(u):
    try:
        return u.split("://")[1].split(".wikipedia")[0]
    except Exception:
        return config.WIKI_LANG


def _clean(node):
    for x in node.select("sup.reference, .mw-editsection, style, .noprint"):
        x.decompose()


def _summary(soup):
    body = soup.select_one("div.mw-parser-output")
    if not body:
        return None
    out = []
    for el in body.find_all("p", recursive=True):
        if el.find_previous("h2"):
            break
        _clean(el)
        t = el.get_text(" ", strip=True)
        if t:
            out.append(t)
    return "\n\n".join(out) or None


def _infobox(soup):
    box = soup.select_one("table.infobox")
    if not box:
        return {}
    d = {}
    for tr in box.select("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            _clean(th)
            _clean(td)
            k, v = th.get_text(" ", strip=True), td.get_text(" ", strip=True)
            if k and v:
                d[k] = v
    return d


def _heading_info(el):
    nm = getattr(el, "name", None)
    if nm in ("h2", "h3", "h4", "h5"):
        h = el.find("span", class_="mw-headline") or el
        return int(nm[1]), h.get_text(" ", strip=True)
    if nm == "div" and any(c.startswith("mw-heading") for c in (el.get("class") or [])):
        h = el.find(["h2", "h3", "h4", "h5"])
        if h:
            return int(h.name[1]), h.get_text(" ", strip=True)
    return None


def _sections(soup):
    body = soup.select_one("div.mw-parser-output")
    secs = []
    if not body:
        return secs
    cur = None
    for el in body.children:
        info = _heading_info(el)
        if info:
            if cur:
                secs.append(cur)
            cur = {"level": info[0], "heading": info[1], "content": ""}
            continue
        nm = getattr(el, "name", None)
        if cur is not None and nm in ("p", "ul", "ol", "dl"):
            _clean(el)
            t = el.get_text(" ", strip=True)
            if t:
                cur["content"] += (("\n" if cur["content"] else "") + t)
    if cur:
        secs.append(cur)
    return secs


def _tables(soup):
    out = []
    for t in soup.select("table.wikitable"):
        rows = []
        for tr in t.select("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            out.append(rows)
    return out


def _refs(soup):
    out = []
    for li in soup.select("ol.references li"):
        _clean(li)
        t = li.get_text(" ", strip=True)
        if t:
            out.append(t)
    return out


def scrape(topic, url=None):
    if url:
        lang = _lang_from_url(url)
        title = _title_from_url(url)
    else:
        lang = config.WIKI_LANG
        # Try original language first
        title = search_page(topic, lang)
        if not title:
            # Fallback to EN Wikipedia
            title = search_page(topic, "en")
            if title:
                lang = "en"
        if not title:
            # Web search fallback: cari URL Wikipedia via DuckDuckGo
            title, fallback_lang = _web_search_fallback(topic)
            if title:
                lang = fallback_lang
                log.info("Web search fallback berhasil: '%s' → %s/%s", topic, lang, title)
        if not title:
            raise ValueError(f"Halaman Wikipedia tidak ditemukan: {topic}")

    r = _request_with_retry(_api(lang), params={
        "action": "parse", "page": title,
        "prop": "text|categories|displaytitle", "format": "json", "redirects": 1
    }, timeout=60)
    if not r or r.status_code != 200:
        raise ValueError(f"Wikipedia API error (status={r.status_code if r else 'N/A'}): {topic}")
    pj = r.json()
    if "error" in pj:
        raise ValueError(pj["error"].get("info", "parse error"))

    parse = pj["parse"]
    real_title = BeautifulSoup(parse.get("displaytitle", title), "lxml").get_text()
    soup = BeautifulSoup(parse["text"]["*"], "lxml")

    resolved_title = parse.get("title", title)
    source_url = "https://{}.wikipedia.org/wiki/{}".format(
        lang, quote(resolved_title.replace(" ", "_"))
    )
    return {
        "title": real_title,
        "source_url": source_url,
        "last_accessed": datetime.datetime.utcnow().isoformat() + "Z",
        "lang": lang,
        "summary": _summary(soup),
        "infobox": _infobox(soup),
        "sections": _sections(soup),
        "tables": _tables(soup),
        "references": _refs(soup),
        "categories": [c["*"] for c in parse.get("categories", [])],
    }
