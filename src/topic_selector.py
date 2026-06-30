"""Topic selector — pick random topics from topic_bank.yaml.

Supports TWO YAML formats:
  Format A (simple):
    misteri:
      - Segitiga Bermuda
      - Area 51

  Format B (rich):
    misteri:
      description: Misteri Dunia
      topics:
        - topic: Segitiga Bermuda
          engagement_score: 9
          tags: [laut, segitiga]
          url: https://...
"""
import random, os, yaml

BANK_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "topic_bank.yaml")
_cache = {"data": None, "mtime": 0}

# Default category descriptions
_DESC = {
    "misteri": "Misteri & Konspirasi",
    "sejarah_gelap": "Sejarah Kelam",
    "tokoh": "Tokoh & Biografi",
    "bencana": "Bencana & Tragedi",
    "fenomena_alam": "Fenomena Alam",
    "budaya_unik": "Budaya & Tradisi Unik",
}


def _load():
    if not os.path.exists(BANK_PATH):
        return {}
    mt = os.path.getmtime(BANK_PATH)
    if _cache["data"] is not None and _cache["mtime"] == mt:
        return _cache["data"]
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _cache["data"] = data
    _cache["mtime"] = mt
    return data


def _get_topics_list(cat_data):
    """Extract topic list from either format."""
    if isinstance(cat_data, list):
        return cat_data
    if isinstance(cat_data, dict) and "topics" in cat_data:
        return cat_data["topics"]
    return []


def _topic_name(t):
    """Get topic name string from either a plain string or rich dict."""
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return t.get("topic", t.get("name", ""))
    return str(t)


def _topic_score(t):
    """Get engagement score (default 5)."""
    if isinstance(t, dict):
        return t.get("engagement_score", 5)
    return 5


def _topic_url(t):
    """Get URL if exists."""
    if isinstance(t, dict):
        return t.get("url")
    return None


def _topic_tags(t):
    if isinstance(t, dict):
        return t.get("tags", [])
    return []


def _topic_notes(t):
    if isinstance(t, dict):
        return t.get("notes", "")
    return ""


def list_categories():
    """Tampilkan semua kategori + jumlah topik."""
    data = _load()
    cats = []
    for key in ("misteri", "sejarah_gelap", "tokoh", "bencana", "fenomena_alam", "budaya_unik"):
        if key not in data:
            continue
        cat_data = data[key]
        topics = _get_topics_list(cat_data)
        desc = _DESC.get(key, key)
        if isinstance(cat_data, dict):
            desc = cat_data.get("description", desc)
        cats.append({
            "id": key,
            "description": desc,
            "count": len(topics),
        })
    return cats


def random_topic(category):
    """Pilih 1 topik random dari kategori, weighted by engagement_score."""
    data = _load()
    cat_data = data.get(category)
    if not cat_data:
        raise ValueError(
            f"Kategori '{category}' tidak ada. Pilihan: {list(data.keys())}"
        )
    topics = _get_topics_list(cat_data)
    if not topics:
        raise ValueError(f"Kategori '{category}' kosong (0 topik). Generate topic bank dulu.")
    weights = [max(_topic_score(t), 1) for t in topics]
    chosen = random.choices(topics, weights=weights, k=1)[0]

    desc = _DESC.get(category, category)
    if isinstance(cat_data, dict):
        desc = cat_data.get("description", desc)

    return {
        "topic": _topic_name(chosen),
        "url": _topic_url(chosen),
        "engagement_score": _topic_score(chosen),
        "tags": _topic_tags(chosen),
        "notes": _topic_notes(chosen),
        "category": desc,
    }


def random_batch(category, n=3):
    """Pilih N topik random tanpa duplikat, weighted by engagement_score."""
    data = _load()
    cat_data = data.get(category)
    if not cat_data:
        raise ValueError(
            f"Kategori '{category}' tidak ada. Pilihan: {list(data.keys())}"
        )
    topics = _get_topics_list(cat_data)
    if not topics:
        raise ValueError(f"Kategori '{category}' kosong (0 topik). Generate topic bank dulu.")
    weights = [max(_topic_score(t), 1) for t in topics]
    n = min(n, len(topics))
    picked = []
    seen_indices = set()
    for _ in range(n):
        available = [(i, t, w) for i, (t, w) in enumerate(zip(topics, weights)) if i not in seen_indices]
        if not available:
            break
        indices, avail_topics, avail_weights = zip(*available)
        chosen = random.choices(range(len(avail_topics)), weights=avail_weights, k=1)[0]
        t = avail_topics[chosen]
        picked.append({
            "topic": _topic_name(t),
            "url": _topic_url(t),
            "engagement_score": _topic_score(t),
            "tags": _topic_tags(t),
            "notes": _topic_notes(t),
        })
        seen_indices.add(indices[chosen])

    desc = _DESC.get(category, category)
    if isinstance(cat_data, dict):
        desc = cat_data.get("description", desc)

    return {
        "category": desc,
        "count": len(picked),
        "topics": picked,
    }


def random_from_all(n=1):
    """Pilih N topik random dari SEMUA kategori, weighted by score."""
    data = _load()
    all_topics = []
    for key in data:
        topics = _get_topics_list(data[key])
        desc = _DESC.get(key, key)
        if isinstance(data[key], dict):
            desc = data[key].get("description", desc)
        for t in topics:
            all_topics.append({
                "_name": _topic_name(t),
                "_url": _topic_url(t),
                "_score": _topic_score(t),
                "_tags": _topic_tags(t),
                "_notes": _topic_notes(t),
                "_cat": key,
                "_cat_desc": desc,
            })
    if not all_topics:
        raise ValueError("Topic bank kosong di semua kategori. Generate topic bank dulu.")
    weights = [max(t["_score"], 1) for t in all_topics]
    n = min(n, len(all_topics))
    picked = random.choices(all_topics, weights=weights, k=n)
    # dedup
    seen = set()
    result = []
    for p in picked:
        if p["_name"] not in seen:
            seen.add(p["_name"])
            result.append({
                "topic": p["_name"],
                "url": p["_url"],
                "engagement_score": p["_score"],
                "tags": p["_tags"],
                "notes": p["_notes"],
                "category": p["_cat_desc"],
            })
    return result[:n]
