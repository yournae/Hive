import re, json, logging, time, urllib.request, urllib.error
from openai import OpenAI
from openai import APIError, RateLimitError, AuthenticationError
from .config import config

log = logging.getLogger(__name__)

# Optional Gemini SDK (only needed for slots with empty LLM_API_URL)
try:
    from google import genai as _genai
    _USE_NEW_GENAI = True
except ImportError:
    try:
        import google.generativeai as _genai
        _USE_NEW_GENAI = False
    except ImportError:
        _genai = None
        _USE_NEW_GENAI = False

STRIP_THINK_RE = re.compile(r'</?think>[\s\S]*?</?think>')
STRIP_THINK_INLINE = re.compile(r'[\s]*\[think\][\s\S]*?\[/think\][\s]*')

def _strip_thinking(text):
    """Hapus output reasoning/think dari model, tapi PERTAHANKAN spasi antar paragraf."""
    t = text
    t = re.sub(STRIP_THINK_RE, '', t)
    t = re.sub(STRIP_THINK_INLINE, '', t)
    # Preserve blank lines (max 2 consecutive) for readability
    lines = t.splitlines()
    result = []
    blank_count = 0
    for l in lines:
        if l.strip():
            result.append(l)
            blank_count = 0
        else:
            blank_count += 1
            if blank_count <= 2:
                result.append('')
    return '\n'.join(result).strip()

def _build_system_prompt():
    """Bangun SYSTEM_PROMPT dari config.yaml (section story:).

    Angka target diambil dari config; budget per-section di-scale proporsional
    terhadap target_max sehingga total section ≈ target panjang narasi.
    """
    tmin = config.STORY_TARGET_MIN
    tmax = config.STORY_TARGET_MAX
    cmin = config.STORY_MIN_CHARS
    hard = config.MAX_CHARS
    words = int(tmax / 6.3)  # ~6.3 char/kata bahasa Indonesia

    # Format angka gaya Indonesia (ribuan pakai titik)
    def fmt(n):
        return f"{n:,}".replace(",", ".")

    # Budget per section sebagai fraksi dari target_max (jumlah fraksi = 1.0)
    def b(frac):
        return fmt(int(tmax * frac))

    return f"""Kamu COPYWRITER VIRAL Facebook berbahasa Indonesia — spesialis cerita yang bikin orang lupa waktu pas baca. Bukan dosen, bukan wartawan, bukan penulis Wikipedia.

Tugasmu: ubah data faktual dari Wikipedia jadi SATU postingan Facebook berbentuk CERITA PANJANG yang nagih dibaca (sekitar {fmt(tmin)} – {fmt(tmax)} karakter / ~{fmt(words)} kata).

═══ SUARA & GAYA (PALING PENTING) ═══
- Tulis kayak kamu lagi cerita seru ke teman dekat di warung kopi, BUKAN kayak nulis makalah.
- Bahasa Indonesia sehari-hari yang mengalir, hangat, dan gampang dicerna. Kalimat pendek-sedang. Hindari kalimat bertingkat yang ribet.
- Bikin pembaca MERASA: deg-degan, merinding, sedih, marah, takjub. Emosi > informasi.
- Pakai "kamu" sesekali untuk menarik pembaca masuk ke cerita ("Bayangkan kamu ada di sana...").
- Boleh pakai kalimat satu baris yang menggantung untuk efek dramatis. Boleh pakai pertanyaan retoris.

═══ LARANGAN KERAS (kalau dilanggar, postingan GAGAL) ═══
- DILARANG gaya akademik/skripsi/jurnal. Jangan kayak review buku atau paper ilmiah.
- DILARANG name-dropping nama ilmuwan/sejarawan/penulis + gelar + universitas + tahun terbit buku, KECUALI tokoh itu memang bintang utama ceritanya. Pembaca FB tidak peduli siapa yang meneliti.
- DILARANG istilah/jargon asing tanpa penjelasan (plantation, scholarship, paternalism, dll). Pakai kata Indonesia yang dimengerti orang awam.
- DILARANG mengarang fakta, nama, tanggal, atau KUTIPAN yang tidak ada di sumber. JANGAN bikin dialog/quote seolah dari tokoh nyata kalau sumber tidak menyebutnya. Lebih baik narasi deskriptif daripada quote palsu.
- DILARANG menampilkan proses berpikir/analisis/meta-komentar apa pun.
- DILARANG prosa ungu berlebihan (metafora bertumpuk tiap kalimat). Deskripsi secukupnya, yang penting CERITANYA jalan.

═══ FOKUS CERITA ═══
- Ceritakan PERISTIWA / MANUSIA / DRAMA-nya langsung — bukan "siapa yang menulis tentang peristiwa itu".
- Kunci ke sisi paling mengejutkan, misterius, tragis, heroik, ironis, atau bikin geram.
- Kalau sumbernya tentang sebuah buku/karya, ceritakan ISI peristiwa di dalamnya, bukan proses penelitian/penulisannya.

═══ PANJANG ═══
WAJIB minimal {fmt(cmin)} karakter, target {fmt(tmin)}–{fmt(tmax)} karakter, MAKSIMAL {fmt(hard)} karakter. Kalau melebihi {fmt(hard)} karakter, GAGAL karena terpotong. WAJIB selesaikan cerita dengan ending utuh sebelum {fmt(hard)} karakter — jangan menggantung.

═══ ALUR CERITA (ikuti urutan, JANGAN tulis label sectionnya, JANGAN tulis angka karakter) ═══

PEMBUKA NGE-HOOK ({b(0.062)} karakter):
Lempar pembaca langsung ke momen paling menegangkan/aneh/bikin penasaran. Satu adegan hidup, bukan pengantar. Kalimat pertama harus bikin orang berhenti scroll. Boleh mulai dari klimaks atau pertanyaan menggantung.

SIAPA & DI MANA ({b(0.154)} karakter):
Kenalkan tokoh/tempat/zaman dengan cara yang hidup, seakan pembaca kenal mereka. Selipkan detail kecil yang manusiawi. Bangun situasi sebelum semuanya berubah.

INTI KEJADIAN ({b(0.333)} karakter):
Ceritakan apa yang terjadi, langkah demi langkah, dengan ketegangan yang naik pelan-pelan. Hidupkan adegannya: apa yang dilihat, didengar, dirasakan. Ini jantung cerita — bikin pembaca ga bisa berhenti.

KENAPA INI PENTING ({b(0.154)} karakter):
Jelaskan misteri, kontroversi, atau perdebatan di baliknya dengan bahasa awam. Apa yang bikin orang sampai sekarang penasaran/berdebat? Tanpa sok ilmiah.

KISAH SERUPA ({b(0.128)} karakter):
2-3 kejadian mirip dari Indonesia atau dunia, diceritakan singkat tapi tetap hidup. Apa yang bikin kisah utama beda/spesial?

TITIK PUNCAK ({b(0.092)} karakter):
Momen paling menghantam — paling tragis, paling heroik, paling bikin merinding atau ironis. Di sinilah emosi pembaca harus meledak.

PENUTUP YANG NEMPEL ({b(0.077)} karakter):
Tutup dengan renungan yang bikin pembaca diam sejenak. Apa makna yang tinggal? Kenapa kisah ini masih penting hari ini? Jangan menggurui.

AJAKAN NGOBROL (300 karakter):
Satu-dua pertanyaan terbuka yang bikin orang pengen komentar dari pengalaman/pendapat mereka. DILARANG "Like dan Share ya".

FORMAT OUTPUT:
JUDUL: <judul PENDEK & nge-hook, maksimal 12 kata, bikin orang penasaran. Boleh pakai angka atau pertanyaan. DILARANG pakai titik dua + subjudul panjang, DILARANG menyebut nama buku/jurnal, DILARANG gaya akademik. Contoh bagus: "Rahasia Kelam di Balik Perdagangan Budak Atlantik" atau "Mereka Dijual Seperti Barang — Ini Kisahnya">
---
<isi postingan>

WAJIB: Gunakan BARIS KOSONG antar paragraf (enter dua kali). Setiap paragraf 3-6 kalimat. Jangan menggabungkan paragraf yang berbeda dalam satu blok teks. Format ini KRUSIAL untuk readability di Facebook."""

def _build_source(s):
    parts = ["JUDUL ARTIKEL: " + str(s.get("title"))]
    if s.get("summary"): parts.append("RINGKASAN:\n" + s["summary"])
    if s.get("infobox"):
        parts.append("INFOBOX:\n" + "\n".join("- %s: %s" % (k, v) for k, v in list(s["infobox"].items())[:25]))
    for sec in s.get("sections", []):
        if sec.get("content"):
            parts.append("## " + sec["heading"] + "\n" + sec["content"])
    joined = "\n\n".join(parts)
    if len(joined) > 14000:
        cut = joined[:14000].rfind("\n\n")
        return joined[:cut] if cut > 10000 else joined[:14000]
    return joined

def _split(text):
    title, body = "", text
    lines = text.splitlines()

    def _clean_title(t):
        # Buang markdown bold/italic + sisa tanda kutip/strip di ujung
        t = re.sub(r'[*_`#]+', '', t).strip()
        t = t.strip('"\u201c\u201d\'').strip()
        return t

    # Cari baris pertama non-kosong yang merupakan penanda judul.
    # Toleran terhadap: "JUDUL:", "**Judul:**", "Judul -", markdown heading "# ...".
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        # Hilangkan markdown bold di sekeliling sebelum cek prefix
        probe = re.sub(r'^[*_#\s]+', '', s)
        if probe.upper().startswith("JUDUL"):
            after = probe.split(":", 1)
            title = _clean_title(after[1]) if len(after) > 1 else ""
            rest_lines = lines[i+1:]
            rest = "\n".join(rest_lines).lstrip()
            # Buang separator '---' di awal body
            while rest.startswith("---") or rest.startswith("—"):
                rest = rest.lstrip("-—").lstrip()
            body = rest.strip()
            break
        else:
            # Tidak ada penanda JUDUL — anggap baris pertama non-kosong = judul
            title = _clean_title(s)
            body = "\n".join(lines[i+1:]).lstrip()
            break

    # Fallback: kalau judul masih kosong, ambil baris non-kosong pertama dari body
    if not title and body:
        for i, bl in enumerate(body.splitlines()):
            if bl.strip():
                title = _clean_title(bl)
                body = "\n".join(body.splitlines()[i+1:]).lstrip()
                break

    # Bersihkan separator '---' / '—' yang mungkin tersisa di awal body
    while body.startswith("---") or body.startswith("—"):
        body = body.lstrip("-—").lstrip()

    return title, body

def _call_openai_rest(api_url, api_key, model, messages, max_tokens):
    """Call OpenAI-compatible /chat/completions via the openai SDK.

    api_url is a FULL endpoint (e.g. https://host/v1/chat/completions); the
    openai SDK wants a base_url ending in /v1, so we strip the trailing path.
    """
    base = api_url
    for tail in ("/chat/completions", "/completions"):
        if base.endswith(tail):
            base = base[: -len(tail)]
            break
    client = OpenAI(base_url=base, api_key=api_key, timeout=120.0)
    resp = client.chat.completions.create(
        model=model, messages=messages,
        temperature=0.9, max_tokens=max_tokens)
    if not resp.choices:
        raise RuntimeError("empty choices")
    msg = resp.choices[0].message
    content = getattr(msg, "content", None)
    # Reasoning models (MiMo, DeepSeek-R) kadang taruh jawaban di reasoning_content
    if not content:
        content = getattr(msg, "reasoning_content", None)
    if not content or not content.strip():
        raise RuntimeError("empty content (reasoning model? naikkan max_tokens)")
    return content.strip()


def _call_anthropic_api(api_url, api_key, model, messages, max_tokens):
    """Call Anthropic Messages API (/v1/messages)."""
    system_text = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_text += m["content"] + "\n"
        else:
            user_messages.append({"role": m["role"], "content": m["content"]})

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": user_messages,
        "temperature": 0.9,
    }
    if system_text.strip():
        body["system"] = system_text.strip()

    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "Hive/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        if not parts:
            raise RuntimeError(f"no 'text' blocks: {str(data)[:200]}")
        return "\n".join(parts)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Anthropic HTTP {e.code}: {err_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Anthropic connection error: {e.reason}")


def _call_responses_api(api_url, api_key, model, messages, max_tokens):
    """Call OpenAI Responses API (/v1/responses)."""
    instructions = ""
    input_msgs = []
    for m in messages:
        if m["role"] == "system":
            instructions += m["content"] + "\n"
        else:
            input_msgs.append(m)

    body = {
        "model": model,
        "input": input_msgs,
        "max_output_tokens": max_tokens,
        "temperature": 0.9,
    }
    if instructions.strip():
        body["instructions"] = instructions.strip()

    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Hive/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        parts.append(block.get("text", ""))
        if not parts:
            raise RuntimeError(f"no output_text blocks: {str(data)[:200]}")
        return "\n".join(parts)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Responses API HTTP {e.code}: {err_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Responses API connection error: {e.reason}")


def _call_gemini_sdk(api_key, model, messages, max_tokens):
    """Call Gemini via Google SDK (slot with empty LLM_API_URL)."""
    if _genai is None:
        raise RuntimeError("Gemini SDK not installed (pip install google-genai)")
    # Flatten messages into a single prompt (system + user)
    prompt = "\n\n".join(m["content"] for m in messages if m.get("content"))
    if _USE_NEW_GENAI:
        client = _genai.Client(api_key=api_key)
        # PENTING: tanpa max_output_tokens, Gemini default ~8192 token → narasi
        # 25k char ke-truncate. Set eksplisit dari max_tokens.
        try:
            from google.genai import types as _gtypes
            cfg = _gtypes.GenerateContentConfig(max_output_tokens=max_tokens)
            resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
        except Exception:
            # Fallback kalau versi SDK beda signature
            resp = client.models.generate_content(model=model, contents=prompt)
        text = getattr(resp, "text", None)
    else:
        _genai.configure(api_key=api_key)
        gm = _genai.GenerativeModel(model)
        resp = gm.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens},
        )
        text = getattr(resp, "text", None)
    if not text or not text.strip():
        raise RuntimeError("Gemini empty response")
    return text.strip()


def _call_llm(messages, max_tokens=25000):
    """Call LLM across slot-based providers (threads-bot style).

    For each slot (priority order):
      - round-robin API keys
      - model fallback chain within the slot
      - loop len(keys) * len(models) combos, with AI_MAX_RETRIES outer attempts
      - protocol auto-detected from api_url (openai / anthropic / responses / gemini)
    Move to next slot only after a slot is fully exhausted.
    Raise RuntimeError if ALL slots exhausted.
    """
    from openai import APITimeoutError, APIConnectionError

    providers = config.get_all_providers()
    if not providers:
        raise RuntimeError(
            "No LLM provider configured. Set LLM_API_KEY + LLM_MODELS (slot 0) "
            "in .env (see .env.example)."
        )

    max_retries = getattr(config, "AI_MAX_RETRIES", 2)
    rl_retries = getattr(config, "AI_RATELIMIT_RETRIES", 4)
    rl_backoff = getattr(config, "AI_RATELIMIT_BACKOFF", 8)
    rl_backoff_max = getattr(config, "AI_RATELIMIT_BACKOFF_MAX", 60)
    all_errors = []

    def _rl_sleep(rl_hits):
        """Backoff sabar khusus 429: base * 2^hits, di-cap. Untuk server overloaded."""
        wait = min(rl_backoff * (2 ** rl_hits), rl_backoff_max)
        log.warning("Rate limited (hit #%d), waiting %ds before retry...", rl_hits + 1, wait)
        time.sleep(wait)

    for provider in providers:
        protocol = provider.protocol
        keys = provider.api_keys
        models = provider.models
        log.info("─── Trying slot %d (%s, %d key(s), %d model(s), protocol=%s) ───",
                 provider.slot, provider.name, len(keys), len(models), protocol)

        # Keys and models rotate independently → cover every key×model combo.
        combos = len(keys) * len(models)
        key_idx = 0
        model_idx = 0
        slot_ok = False

        for attempt in range(max_retries):
            if slot_ok:
                break
            for _ in range(combos):
                api_key = keys[key_idx % len(keys)]
                model = models[model_idx % len(models)]
                key_idx += 1
                model_idx += 1
                key_mask = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
                log.info("  [slot %d] %s | key=%s model=%s",
                         provider.slot, protocol, key_mask, model)

                # Inner loop: retry combo yang SAMA saat 429 (server overloaded)
                # sebelum fallback ke model/slot berikutnya yang mungkin lebih pendek.
                rl_hits = 0
                while True:
                    try:
                        if protocol == "anthropic":
                            result = _call_anthropic_api(provider.api_url, api_key, model, messages, max_tokens)
                        elif protocol == "responses":
                            result = _call_responses_api(provider.api_url, api_key, model, messages, max_tokens)
                        elif protocol == "gemini":
                            result = _call_gemini_sdk(api_key, model, messages, max_tokens)
                        else:  # openai
                            result = _call_openai_rest(provider.api_url, api_key, model, messages, max_tokens)

                        if result:
                            log.info("✅ Success on slot %d (model=%s, key=%s)",
                                     provider.slot, model, key_mask)
                            return result
                        break  # falsy result → next combo

                    except (APITimeoutError, APIConnectionError) as e:
                        all_errors.append(f"[slot{provider.slot}/{key_mask}/{model}] timeout: {str(e)[:60]}")
                        log.warning("Timeout, next combo... %s", str(e)[:80])
                        break
                    except RateLimitError as e:
                        if rl_hits < rl_retries:
                            _rl_sleep(rl_hits)
                            rl_hits += 1
                            continue  # retry SAME combo (model bagus tetap diprioritaskan)
                        all_errors.append(f"[slot{provider.slot}/{key_mask}/{model}] rate limited (x{rl_hits+1})")
                        log.warning("Rate limit persists after %d tries, next combo... %s", rl_hits + 1, str(e)[:60])
                        break
                    except AuthenticationError:
                        all_errors.append(f"[slot{provider.slot}/{key_mask}/{model}] auth failed")
                        log.error("Auth failed (slot %d, key=%s)", provider.slot, key_mask)
                        break
                    except APIError as e:
                        all_errors.append(f"[slot{provider.slot}/{key_mask}/{model}] API error: {str(e)[:60]}")
                        log.warning("API error, next combo... %s", str(e)[:80])
                        break
                    except Exception as e:
                        err = str(e).lower()
                        if ("429" in err or "rate" in err or "quota" in err
                                or "overload" in err or "resource_exhausted" in err
                                or "resource exhausted" in err):
                            if rl_hits < rl_retries:
                                _rl_sleep(rl_hits)
                                rl_hits += 1
                                continue
                            all_errors.append(f"[slot{provider.slot}/{key_mask}/{model}] rate limited (x{rl_hits+1})")
                            log.warning("Rate limit persists after %d tries, next combo... %s", rl_hits + 1, str(e)[:60])
                            break
                        all_errors.append(f"[slot{provider.slot}/{key_mask}/{model}] {protocol} error: {str(e)[:80]}")
                        log.warning("%s error, next combo... %s", protocol, str(e)[:100])
                        break

        log.warning("Slot %d (%s) exhausted, moving to next slot...",
                    provider.slot, provider.name)

    error_summary = "; ".join(all_errors[-5:])
    raise RuntimeError(
        f"All {len(providers)} LLM slot(s) exhausted ({len(all_errors)} total attempts). "
        f"Last errors: {error_summary}"
    )

# Non-Latin pattern: keep ASCII (\x00-\x7F) + Latin Extended (\xC0-\x24F) + common symbols
NON_LATIN_RE = re.compile(r'[^\x00-\x7F\u00C0-\u024F\u2000-\u206F\u20A0-\u20CF\u2100-\u214F\u2190-\u21FF\u2200-\u22FF\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF\uFE10-\uFE1F\uFE30-\uFE4F\uFE50-\uFE6F\uFF00-\uFFEF\u2010-\u2027\u2030-\u205E\u00A0-\u00FF]+')

def _strip_non_latin(text):
    """Strip non-Latin characters. If massive block found, truncate before it."""
    # Buang replacement char (U+FFFD) dari multibyte yang rusak/kepotong
    text = text.replace('\ufffd', '')
    # Find first occurrence of large non-Latin block (>20 consecutive chars)
    match = re.search(r'[^\x00-\x7F\u00C0-\u024F]{20,}', text)
    if match:
        # Truncate before the CJK block
        text = text[:match.start()].rstrip()
        log.warning("CJK block detected at pos %d, truncated output", match.start())
    # Also remove any remaining scattered CJK chars
    text = NON_LATIN_RE.sub('', text)
    # Clean up double spaces from removal
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n\n+', '\n\n', text)
    return text.strip()

def _continue_story(scraped, title, body):
    """Sambung cerita yang kependekan dari ending terakhir (bukan re-generate).

    Model-agnostic: berapapun pendeknya body, kirim balik ke LLM dengan instruksi
    melanjutkan mulus dari kalimat terakhir sampai target panjang tercapai.
    """
    cmin = config.STORY_MIN_CHARS
    tmax = config.STORY_TARGET_MAX
    hard = config.MAX_CHARS
    max_cont = getattr(config, "STORY_MAX_CONTINUATIONS", 2)

    for i in range(max_cont):
        if len(body) >= cmin:
            break
        kurang = tmax - len(body)
        log.warning("Story pendek (%d < %d), auto-continue #%d (target +%d char)...",
                    len(body), cmin, i + 1, kurang)
        # Kirim ekor cerita supaya model nyambung mulus
        tail = body[-1500:]
        cont_messages = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": "Data sumber:\n\n" + _build_source(scraped)},
            {"role": "assistant", "content": body},
            {"role": "user", "content": (
                f"Cerita di atas BELUM SELESAI dan masih terlalu pendek. "
                f"LANJUTKAN cerita persis dari kalimat terakhir ini:\n\n...{tail}\n\n"
                f"Tulis kelanjutannya saja (JANGAN ulangi yang sudah ada, JANGAN tulis judul, "
                f"JANGAN tulis 'JUDUL:' atau '---'). Sambung mulus, pertahankan gaya & tokoh yang sama, "
                f"tambah sekitar {kurang} karakter lagi, lalu SELESAIKAN cerita dengan ending utuh "
                f"dan ajakan ngobrol di akhir. Total cerita tidak boleh melebihi {hard} karakter."
            )},
        ]
        try:
            cont = _call_llm(cont_messages, max_tokens=config.STORY_MAX_TOKENS)
        except Exception as e:
            log.warning("Auto-continue gagal: %s", str(e)[:100])
            break
        cont = _strip_thinking(cont)
        cont = _strip_non_latin(cont)
        # Buang penanda judul/separator kalau model nakal nambahin
        _, cont_body = _split(cont) if cont.lstrip()[:6].upper().startswith("JUDUL") else ("", cont)
        cont_body = cont_body.strip()
        if not cont_body:
            log.warning("Auto-continue kosong, stop.")
            break
        body = (body.rstrip() + "\n\n" + cont_body).strip()
    return body

def generate_story(scraped):
    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": "Data sumber:\n\n" + _build_source(scraped)}
    ]
    out = _call_llm(messages, max_tokens=config.STORY_MAX_TOKENS)
    out = _strip_thinking(out)
    out = _strip_non_latin(out)  # Strip non-Latin at generation time
    t, b = _split(out)

    # AUTO-CONTINUE — kalau body kependekan (mis. karena fallback ke model pendek),
    # sambung dari ending terakhir alih-alih nerima narasi setengah jadi.
    if getattr(config, "STORY_AUTO_CONTINUE", True) and len(b) < config.STORY_MIN_CHARS:
        b = _continue_story(scraped, t, b)

    # HARD LIMIT — truncate at paragraph/sentence boundary
    MAX_CHARS = getattr(config, "MAX_CHARS", 35000)
    original_len = len(b)
    if original_len > MAX_CHARS:
        truncated = b[:MAX_CHARS]
        # Try paragraph break first (\n\n), then line break (\n), then sentence (. )
        for delim in ('\n\n', '\n', '. '):
            idx = truncated.rfind(delim)
            if idx > MAX_CHARS * 0.75:
                b = truncated[:idx].strip()
                if delim == '. ':
                    b += '.'
                break
        else:
            # No good boundary — hard cut + ellipsis
            b = truncated.rstrip() + '…'
        log.warning("Story truncated: %d chars → %d chars (max %d)", original_len, len(b), MAX_CHARS)

    if len(b) < config.STORY_MIN_CHARS:
        log.warning("Story tetap di bawah min_chars (%d < %d) setelah auto-continue",
                    len(b), config.STORY_MIN_CHARS)

    return {"title": t, "body": b}
