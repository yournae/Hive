<div align="center">

# 🐝 Hive

**Robot yang otomatis bikin & posting artikel ke Halaman Facebook.**

Ambil topik dari Wikipedia → AI tulis cerita panjang → posting ke Facebook sesuai jadwal.

<img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
<img src="https://img.shields.io/badge/platform-Facebook%20Pages-1877F2?logo=facebook&logoColor=white" alt="Facebook">
<img src="https://img.shields.io/badge/license-MIT-orange" alt="MIT">

</div>

---

## Ini buat apa? (baca ini dulu)

Hive adalah **mesin konten otomatis untuk Halaman Facebook**. Kamu kasih daftar topik,
sisanya dia yang kerja: ambil bahan dari Wikipedia, suruh AI menulis artikel panjang,
lalu posting ke Facebook sesuai jadwal — tanpa kamu sentuh.

Bayangkan jalur pabrik 4 tahap:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  1. TOPIK    │────▶│  2. AMBIL    │────▶│  3. TULIS    │────▶│  4. POSTING  │
│              │     │              │     │              │     │              │
│ Bank Topik   │     │ Wikipedia    │     │ AI (banyak   │     │ Facebook     │
│ 1000+ topik  │     │ (ID / EN)    │     │ penyedia)    │     │ Graph API    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

| # | Tahap | Tugasnya |
|:--|:------|:---------|
| 1 | 🎯 **Topik** | Ambil 1 topik dari bank topik (1000+ topik siap pakai) |
| 2 | 🔍 **Ambil (scrape)** | Unduh isi artikel Wikipedia tentang topik itu |
| 3 | 📝 **Tulis** | AI mengubahnya jadi cerita panjang (16.000+ karakter) |
| 4 | 📤 **Posting** | Unggah ke Halaman Facebook lewat Graph API |

> **Istilah penting:**
> - **Scrape** = mengunduh isi halaman web otomatis.
> - **LLM / AI** = model seperti ChatGPT/Gemini yang menulis cerita.
> - **Graph API** = pintu resmi Facebook untuk posting via program.
> - **Daemon / scheduler** = program yang jalan 24 jam di latar belakang sesuai jadwal.
> - **Token** = "tiket masuk" untuk posting via API Facebook.
> - **Bank topik** = daftar besar topik siap pakai, dikelompokkan per kategori.

---

## ✨ Fitur singkat

| | Fitur | Penjelasan |
|:--|:------|:-----------|
| 🔍 | **Scraper Wikipedia** | Multi-bahasa, pencocokan topik pintar, anti-blokir `curl_cffi` |
| 📝 | **Penulis AI** | Cerita panjang via banyak penyedia LLM, auto-pindah kalau gagal, auto-sambung kalau kependekan |
| 📤 | **Poster Facebook** | Graph API, potong rapi di batas kalimat, token Halaman otomatis |
| ⏰ | **Scheduler 24/7** | Auto-posting di jam tertentu, ada jam istirahat + ringkasan harian |
| 🎯 | **Bank Topik** | 1.000+ topik di 6 kategori |
| 💬 | **Menu interaktif** | Menu bertingkat untuk semua aksi |
| 📊 | **Dashboard web** | Pantau status real-time di port lokal |
| 🔔 | **Notifikasi Telegram** | Kabar saat mulai/posting/error/ringkasan harian |

---

## 🚀 Persiapan (setup) — lakukan sekali

```bash
# 1. Ambil kodenya
git clone https://github.com/lnxnil/Hive.git
cd Hive

# 2. Buat lingkungan Python terpisah (venv) + pasang paket
python3 -m venv venv
source venv/bin/activate          # ← jalankan SETIAP buka terminal baru
pip install -r requirements.txt

# 3. Isi kunci API & kredensial Facebook
cp .env.example .env
nano .env                         # isi, lalu simpan: Ctrl+O Enter Ctrl+X

# 4. Jalankan menu interaktif (cara paling gampang)
python3 run.py menu
```

> ⚠️ **Perhatikan:** proyek ini pakai folder venv bernama **`venv`** (bukan `.venv`).
> **Setiap buka terminal baru**, jalankan dulu `source venv/bin/activate`. Kalau lupa
> → error "module not found".

> **Pertama kali jalan?** Bank topik dibuat sesuai kebutuhan. Dari menu, pilih
> **🎯 Pick Topic → Categories** untuk mengisinya, atau jalankan
> `python3 run.py batch <kategori> 10`.

---

## 🧭 Peta menu

```
🐝 HIVE
├── 1) 📊  Status & Statistik
├── 2) 🔍  Browse Artikel      → semua / per status / per ID / hapus
├── 3) 🎯  Pick Topic          → Random / Batch / Luck / Manual / Categories
├── 4) 📝  Generate Story      → per ID / Batch / Scrape+Generate / CJK Clean / Re-generate
├── 5) 📤  Publish ke Facebook → Next / per ID / Batch / Recent / Cek Token / Reset Failed / Schedule
├── 6) 🔧  System & Tools      → Init DB / Tes Telegram / Dashboard / Scheduler / CLI Ref / Export CSV
└── 0)  Keluar
```

---

## ⌨️ Daftar perintah (CLI)

```bash
# ── Status ──
python3 run.py status                   # statistik pipeline
python3 run.py list                     # daftar artikel

# ── Memilih topik ──
python3 run.py random <kategori>        # 1 topik acak
python3 run.py batch <kategori> [n]     # N topik sekaligus (default 3)
python3 run.py luck [n]                 # N topik dari semua kategori
python3 run.py categories               # daftar kategori + jumlahnya

# ── Ambil & tulis ──
python3 run.py scrape "Nama Topik"      # ambil artikel Wikipedia
python3 run.py add "Nama Topik"         # ambil + langsung tulis cerita
python3 run.py story <id>               # tulis cerita untuk 1 artikel
python3 run.py show <id>                # lihat pratinjau cerita

# ── Posting ──
python3 run.py publish                  # posting berikutnya dari antrian
python3 run.py publish <id>             # posting artikel tertentu
python3 run.py publish-all [n]          # posting beberapa sekaligus (default 5)

# ── Server ──
python3 run.py serve                    # dashboard web
python3 run.py schedule                 # daemon scheduler (di depan layar)

# ── Lain-lain ──
python3 run.py initdb                   # siapkan database (sekali di awal)
```

> Beberapa perintah punya alias: `categories` = `category` / `cat`; `list` = `ls` /
> `articles`. `scrape` & `add` juga menerima `--url <link>` untuk memaksa URL Wikipedia tertentu.

---

## 🔄 Jalan 24/7 otomatis (systemd)

```bash
# Catatan: file unit menganggap proyek ada di /opt/hive.
# Kalau kamu deploy di tempat lain, edit path di fb-pipeline.service dulu.
sudo cp fb-pipeline.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fb-pipeline
journalctl -u fb-pipeline -f            # lihat log live
```

> 💡 **Tips deploy:** menu **System & Tools → Scheduler** bisa membuat/memperbaiki
> file service otomatis sesuai lokasi & venv checkout kamu — jadi clone di path/user
> mana pun tetap jalan tanpa edit manual.

- **Jadwal** — diatur di `config.yaml` (default `08:00`, `13:00`, `20:00`).
- **Jam istirahat** — `22:00 – 06:00`, tidak posting.
- **Auto-tulis** — kalau stok cerita menipis, cerita baru dibuat otomatis.

---

## ⚙️ Pengaturan

### Kunci & kredensial (`.env`)

| Variabel | Isinya |
|:---------|:-------|
| `LLM_API_KEY` / `LLM_API_KEYS` | Kunci slot 0 (`KEYS` = banyak kunci, rotasi round-robin) |
| `LLM_API_URL` | Endpoint slot 0 (kosong → Gemini SDK) |
| `LLM_MODELS` | Model slot 0 (pisah koma → dicoba bergantian) |
| `LLM_API_KEY_N` / `LLM_API_KEYS_N` | Kunci slot N (`N` = 1–9) |
| `LLM_API_URL_N` / `LLM_MODELS_N` | Endpoint / model slot N |
| `AI_MAX_RETRIES` | Coba ulang per slot (1–10, default `2`) |
| `FB_PAGE_ID` | ID Halaman Facebook |
| `FB_PAGE_ACCESS_TOKEN` | Token Akses Halaman (token User otomatis dikonversi ke token Page) |
| `FB_APP_ID` / `FB_APP_SECRET` | Kredensial App (untuk tukar token jangka panjang) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Notifikasi Telegram (opsional) |

### Penyetelan (`config.yaml`)

```yaml
wikipedia:
  lang: id                # bahasa Wikipedia sumber (id = Indonesia, en = Inggris)

facebook:
  api_version: v21.0      # versi Graph API

schedule:
  timezone: Asia/Jakarta
  mode: fixed             # "fixed" = posting di jam tetap (times di bawah)
                          # "interval" = posting tiap N jam mulai start_hour
  times: ["08:00", "13:00", "20:00"]   # dipakai saat mode: fixed
  interval_hours: 4       # dipakai saat mode: interval (posting tiap berapa jam)
  start_hour: 8           # dipakai saat mode: interval (jam mulai)
  rest_start: 22          # mulai jam istirahat
  rest_end: 6             # selesai jam istirahat

auto_generate:
  stock_min: 5            # auto-tulis cerita baru kalau stok di bawah ini
  batch_size: 3           # berapa cerita per batch auto-tulis

publish:
  max_retries: 3
  max_chars: 20000        # BATAS POTONG FINAL satu postingan Facebook

story:                    # target panjang yang DIMINTA ke AI
  min_chars: 16000        # minimum
  target_min: 18000       # target bawah
  target_max: 19500       # target atas
  max_tokens: 25000       # batas teknis output LLM
  auto_continue: true     # kalau kependekan, sambung (bukan tulis ulang)
  max_continuations: 2    # maks berapa kali menyambung sebelum menyerah

ai:                       # ketahanan terhadap rate-limit (429)
  max_retries: 2          # percobaan luar per slot
  ratelimit_retries: 4    # ulang combo SAMA saat 429 sebelum pindah model
  ratelimit_backoff: 8    # detik, jeda dasar (8 → 16 → 32 → ...)
  ratelimit_backoff_max: 60   # batas jeda per ulangan
```

> ⚠️ **Penting:** `publish.max_chars` adalah **pemotongan final yang keras**.
> Sedangkan `story.*` adalah panjang yang **diminta** ke AI. Pastikan
> `max_chars ≥ target_max`, kalau tidak hasil tulisan AI akan kepotong.

---

## 🧠 Sistem AI multi-penyedia (slot)

Cerita ditulis AI. Kamu bisa pasang sampai **10 penyedia** dalam bentuk "slot"
(slot 0 = utama, slot 1–9 = cadangan):

```
slot 0 (utama) ──habis──▶ slot 1 ──habis──▶ slot 2 ...
     │                         │
     ▼                         ▼
 kombinasi kunci × model    kombinasi kunci × model
 (kunci dirotasi,           (kunci dirotasi,
  model dicoba bergantian)   model dicoba bergantian)
```

- Slot aktif **hanya kalau** punya **minimal 1 kunci DAN 1 model**. Slot kosong/setengah
  dilewati otomatis. Boleh ada lompatan nomor (misal slot `0, 1, 5`).
- Kalau semua slot gagal, sistem berhenti rapi (tidak crash).

**Format API terdeteksi otomatis dari `LLM_API_URL_N`:**

| Akhiran URL | Protokol | Header auth |
|:------------|:---------|:------------|
| `…/chat/completions` | OpenAI-compatible | `Authorization: Bearer` |
| `…/messages` | Anthropic Messages API | `x-api-key` |
| `…/responses` | OpenAI Responses API | `Authorization: Bearer` |
| *(URL kosong)* | Gemini SDK (`google-genai`) | dikelola SDK |

> **Model "reasoning"** (seperti MiMo, DeepSeek-R) yang menaruh jawaban di
> `reasoning_content`, bukan `content`, ditangani otomatis — tidak perlu setel apa pun.

---

## 📚 Bank Topik

| Kategori | Perkiraan jumlah | Contoh |
|:---------|:-----------------|:-------|
| `misteri` | ~170 | Segitiga Bermuda, Area 51 |
| `sejarah_gelap` | ~185 | Peristiwa sejarah kelam |
| `tokoh` | ~200 | Tokoh terkenal |
| `bencana` | ~145 | Bencana alam |
| `fenomena_alam` | ~150 | Fenomena alam |
| `budaya_unik` | ~165 | Tradisi budaya unik |

---

## 🔁 Alur status artikel

```
scraped ──▶ story_ready ──▶ posted
   │              │
   └──────────▶ failed
```

| Status | Artinya |
|:-------|:--------|
| `scraped` | Sudah diambil dari Wikipedia, belum ditulis |
| `story_ready` | Cerita sudah ditulis, siap posting |
| `posted` | Sudah terbit di Facebook |
| `failed` | Gagal (bisa di-reset & dicoba lagi) |

---

## 📁 Struktur proyek

```
Hive/
├── run.py                  # entry CLI (menu + perintah)
├── main.py                 # entry daemon (scheduler)
├── config.yaml             # jadwal, publish, story, retry
├── .env.example            # contoh pengaturan — salin ke .env
├── requirements.txt
├── fb-pipeline.service     # template unit systemd
├── data/
│   ├── topic_bank.yaml     # bank topik (dibuat otomatis, gitignored)
│   ├── pipeline.db         # database SQLite (gitignored)
│   ├── scraped/            # artikel hasil scrape (JSON, gitignored)
│   └── stories/            # cerita hasil tulis (gitignored)
├── scripts/
│   └── clean_cjk.py        # pembersih karakter non-Latin (CJK)
└── src/
    ├── cli_menu.py         # menu interaktif
    ├── config.py           # pembaca .env + config.yaml
    ├── database.py         # operasi SQLite
    ├── dashboard.py        # dashboard web (Flask)
    ├── notifier.py         # notifikasi Telegram
    ├── pipeline.py         # orkestrator (ambil, tulis, posting)
    ├── publisher.py        # klien Facebook Graph API
    ├── scheduler.py        # daemon auto-post
    ├── scraper.py          # scraper Wikipedia
    ├── storyteller.py      # penulis cerita LLM (multi-protokol)
    ├── topic_bank_generator.py  # pembangun bank topik
    └── topic_selector.py   # pengacak bank topik
```

---

## 🛠️ Kalau error / bingung

| Masalah | Penyebab / Solusi |
|:--------|:------------------|
| `ModuleNotFoundError` | Lupa aktifkan venv → `source venv/bin/activate` |
| `FB error: (#100)` | Cek `FB_PAGE_ID` sudah benar |
| `Token not valid` | Pakai Page Access Token, atau biarkan token User dikonversi otomatis |
| Cerita kependekan | LLM kadang keluarkan output pendek; ulang `python3 run.py story <id>` |
| Ada karakter non-Latin (CJK) | Jalankan `python3 scripts/clean_cjk.py` |
| Stok kosong | `python3 run.py batch <kategori> 10`, lalu generate |
| `429 / overloaded` | Backoff bawaan otomatis mengulang; tambah slot LLM biar lebih tahan |

---

## 📄 Lisensi

MIT
