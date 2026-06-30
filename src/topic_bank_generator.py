"""Topic Bank Generator — generate random topics via LLM.

Generates topics across 6 categories and saves to data/topic_bank.yaml.
Run once after fresh clone: python3 run.py menu -> Pilih Topik -> Generate Topic Bank.

Uses batching (50 topics/call) to avoid rate limits and timeouts.
Saves incrementally after each batch so progress isn't lost.

Usage:
  from src.topic_bank_generator import generate_topic_bank
  generate_topic_bank(count_per_category=175)  # ~1050 total
"""
import os, sys, re, yaml, logging, time

log = logging.getLogger(__name__)

BANK_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "topic_bank.yaml")
BATCH_SIZE = 50  # topics per LLM call
COOLDOWN = 15    # seconds between calls
MAX_RETRIES = 3  # retries per batch on 429

CATEGORIES = {
    "misteri": {
        "description": "Misteri & Konspirasi",
        "prompt": (
            "Generate exactly {n} unique mystery, conspiracy, or unexplained phenomenon topics. "
            "Include: famous unsolved cases, secret societies, government conspiracies, "
            "paranormal events, cryptids, lost civilizations, ancient mysteries. "
            "Mix well-known and obscure. Each topic must be a short phrase (2-6 words). "
            "Return ONLY a YAML list, one topic per line, no explanations."
        ),
    },
    "sejarah_gelap": {
        "description": "Sejarah Kelam",
        "prompt": (
            "Generate exactly {n} unique dark history topics. "
            "Include: massacres, genocides, dictatorships, wars, slavery, "
            "human experiments, historical atrocities. "
            "Mix global and lesser-known events. Each topic: short phrase (2-6 words). "
            "Return ONLY a YAML list, one topic per line."
        ),
    },
    "tokoh": {
        "description": "Tokoh & Biografi",
        "prompt": (
            "Generate exactly {n} unique biographical topics about famous/infamous people. "
            "Include: inventors, criminals, dictators, scientists, artists, "
            "revolutionaries, cult leaders, whistleblowers. Mix eras and regions. "
            "Each topic: person name or short phrase. "
            "Return ONLY a YAML list, one topic per line."
        ),
    },
    "bencana": {
        "description": "Bencana & Tragedi",
        "prompt": (
            "Generate exactly {n} unique disaster and tragedy topics. "
            "Include: earthquakes, tsunamis, pandemics, shipwrecks, plane crashes, "
            "nuclear accidents, volcanic eruptions, industrial disasters. "
            "Mix natural and man-made. Each topic: short phrase (2-6 words). "
            "Return ONLY a YAML list, one topic per line."
        ),
    },
    "fenomena_alam": {
        "description": "Fenomena Alam",
        "prompt": (
            "Generate exactly {n} unique natural phenomenon topics. "
            "Include: aurora, bioluminescence, ball lightning, blood rain, "
            "sailing stones, underwater waterfalls, magnetic anomalies, "
            "extreme weather events. Each topic: short phrase (2-6 words). "
            "Return ONLY a YAML list, one topic per line."
        ),
    },
    "budaya_unik": {
        "description": "Budaya & Tradisi Unik",
        "prompt": (
            "Generate exactly {n} unique cultural practices and traditions. "
            "Include: death rituals, festivals, body modifications, "
            "unusual customs, tribal practices, ancient traditions still alive. "
            "Mix global cultures. Each topic: short phrase (2-6 words). "
            "Return ONLY a YAML list, one topic per line."
        ),
    },
}


def _call_with_retry(messages, max_tokens=4000):
    """Call LLM with retry on 429. Returns response text or None."""
    from src.storyteller import _call_llm

    for attempt in range(MAX_RETRIES):
        try:
            result = _call_llm(messages, max_tokens=max_tokens)
            return result
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower() or "overloaded" in err_str.lower():
                wait = COOLDOWN * (attempt + 1)
                log.warning(f"  Rate limited, waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise
    return None


def _parse_topics(text):
    """Parse topic list from LLM response — tahan banting terhadap output real.

    Menangani: YAML list, numbered list (1. / 1)), dash/bullet, markdown bold/italic,
    code fence, thinking block (<think>), quote, dan topik ber-titik-dua
    (mis. 'Unit 731: Human Experiments' yang kalau lewat YAML jadi dict).
    Strategi: line-based, JANGAN andalkan yaml.safe_load (rapuh ke markdown/colon).
    """
    if not text:
        return []

    # 1. Buang thinking block model reasoning (MiMo dkk): <think>...</think>
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Buang thinking block yang ga ketutup
    text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL | re.IGNORECASE)

    topics = []
    seen = set()
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        # Skip code fence & penanda markdown lain
        if line.startswith("```") or line in ("---", "...", "yaml", "- "):
            continue
        # Buang prefix list: "- ", "* ", "• ", "1. ", "1) ", "1- "
        line = re.sub(r'^\s*[-*•·]\s+', '', line)
        line = re.sub(r'^\s*\d+\s*[.)\-]\s+', '', line)
        # Buang markdown bold/italic/code/heading
        line = re.sub(r'[*_`#]+', '', line).strip()
        # Buang quote di ujung
        line = line.strip('"\u201c\u201d\'').strip()
        # Buang trailing colon kosong ("Topik:" tanpa isi) tapi PERTAHANKAN
        # topik ber-colon yang sah ("Unit 731: Human Experiments")
        if line.endswith(":"):
            line = line[:-1].strip()
        # Skip baris yang jelas bukan topik (kalimat penjelasan / intro)
        low = line.lower()
        if not line or len(line) < 2:
            continue
        if low.startswith(("here are", "berikut", "sure", "tentu", "okay", "ok,", "note:", "catatan")):
            continue
        # Topik wajar: <= 12 kata (frasa pendek), buang yang kepanjangan (kalimat)
        if len(line.split()) > 12:
            continue
        # Dedup case-insensitive dalam satu response
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(line)

    return topics


def _save_bank(data):
    """Save topic bank to YAML file."""
    os.makedirs(os.path.dirname(BANK_PATH), exist_ok=True)
    with open(BANK_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _load_bank():
    """Load existing topic bank."""
    if not os.path.exists(BANK_PATH):
        return {}
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_existing_names(cat_data):
    """Get set of existing topic names from category data."""
    if isinstance(cat_data, list):
        return {t if isinstance(t, str) else t.get("topic", "") for t in cat_data}
    if isinstance(cat_data, dict) and "topics" in cat_data:
        return {t if isinstance(t, str) else t.get("topic", "") for t in cat_data["topics"]}
    return set()


def generate_topic_bank(count_per_category=175):
    """Generate topic bank using LLM. Returns (success, message).

    Uses batching (50 topics/call) with cooldown between calls.
    Saves incrementally after each successful batch.
    """
    try:
        from src.config import config
    except ImportError as e:
        return False, f"Import error: {e}"

    existing = _load_bank()
    total_new = 0
    failed_cats = []

    for cat_key, cat_info in CATEGORIES.items():
        cat_data = existing.get(cat_key, [])
        if isinstance(cat_data, dict):
            cat_data = cat_data.get("topics", [])

        existing_names = _get_existing_names(existing.get(cat_key, []))

        if len(cat_data) >= count_per_category:
            log.info(f"[{cat_key}] already has {len(cat_data)} topics, skipping")
            continue

        needed = count_per_category - len(cat_data)
        log.info(f"[{cat_key}] need {needed} more topics (have {len(cat_data)})")

        cat_new = 0
        batch_num = 0
        max_batches = (needed + BATCH_SIZE - 1) // BATCH_SIZE + 2  # extra margin

        while cat_new < needed and batch_num < max_batches:
            batch_num += 1
            batch_target = min(BATCH_SIZE, needed - cat_new)
            prompt = cat_info["prompt"].format(n=batch_target + 10)  # ask for extra

            # Exclude existing to avoid dupes
            exclude_list = list(existing_names)[:80]
            if exclude_list:
                prompt += f"\n\nDo NOT include any of these: {', '.join(exclude_list)}"

            log.info(f"  [{cat_key}] batch {batch_num}: requesting {batch_target} topics...")

            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are a topic research expert. Generate diverse, "
                            "interesting topics for social media content. "
                            "Return ONLY a valid YAML list. Example:\n"
                            "- Topic One\n- Topic Two\n- Topic Three"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
                result = _call_with_retry(messages, max_tokens=2000)

                if not result:
                    log.warning(f"  [{cat_key}] batch {batch_num}: empty response, retrying next batch")
                    time.sleep(COOLDOWN)
                    continue

                new_topics = _parse_topics(result)
                if not new_topics:
                    log.warning(f"  [{cat_key}] batch {batch_num}: no valid YAML list in response")
                    time.sleep(COOLDOWN)
                    continue

                # Deduplicate
                added = 0
                for t in new_topics:
                    name = t if isinstance(t, str) else t.get("topic", "")
                    if name and name not in existing_names:
                        cat_data.append(t)
                        existing_names.add(name)
                        cat_new += 1
                        added += 1
                    if cat_new >= needed:
                        break

                log.info(f"  [{cat_key}] batch {batch_num}: +{added} unique (total new: {cat_new})")

                # Save incrementally after each batch
                existing[cat_key] = cat_data
                _save_bank(existing)

                time.sleep(COOLDOWN)

            except Exception as e:
                log.error(f"  [{cat_key}] batch {batch_num} error: {type(e).__name__}: {e}")
                time.sleep(COOLDOWN)
                continue

        total_new += cat_new
        if cat_new < needed:
            failed_cats.append(f"{cat_key} ({cat_new}/{needed})")
            log.warning(f"[{cat_key}] only got {cat_new}/{needed} topics")
        else:
            log.info(f"[{cat_key}] done: {len(cat_data)} total topics")

    # Final save (already saved incrementally, but just in case)
    _save_bank(existing)

    if total_new == 0:
        log.error("ALL categories returned 0 topics. Check .env and LLM provider config.")
        return False, (
            "Generated 0 topics. Semua provider gagal — cek .env (LLM_API_KEY, "
            "LLM_BASE_URL, LLM_MODEL) dan pastikan kuota provider masih ada."
        )

    total = sum(
        len(v) if isinstance(v, list) else len(v.get("topics", []))
        for v in existing.values()
    )

    if failed_cats:
        return True, (
            f"Generated {total_new} new topics. Total: {total}. "
            f"Incomplete: {', '.join(failed_cats)}. Run again to fill gaps."
        )
    return True, f"Generated {total_new} new topics. Total: {total} across {len(existing)} categories."
