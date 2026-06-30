import os, yaml, threading, logging
from dataclasses import dataclass, field
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger(__name__)

def _y():
    p = os.path.join(BASE_DIR, "config.yaml")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
_c = _y()


# ======================== LLM PROVIDER SLOTS (0-9) ========================
# Slot 0 = primary, slot 1-9 = fallbacks. Each slot is provider-agnostic.
#
# Env vars per slot N (slot 0 uses NO suffix):
#   LLM_API_KEY_N       single key
#   LLM_API_KEYS_N      comma-separated keys → auto-rotate round-robin per request
#   LLM_API_URL_N       full endpoint URL (e.g. https://host/v1/chat/completions)
#   LLM_MODELS_N        comma-separated models → fallback chain within same slot
#
# Protocol auto-detected from LLM_API_URL_N:
#   empty            → Gemini SDK mode (needs google-genai)
#   ".../messages"   → Anthropic Messages API
#   ".../responses"  → OpenAI Responses API
#   anything else    → OpenAI-compatible /chat/completions

@dataclass
class LLMProvider:
    """Unified LLM provider — slot-based, provider-agnostic.

    - slot 0 = primary, slot 1-9 = fallbacks
    - api_keys: auto-rotated round-robin per request
    - models: fallback chain within the same provider
    - api_url: full endpoint URL. Empty = Gemini SDK mode.
    """
    slot: int
    api_key: str = ""
    api_keys: list = field(default_factory=list)
    api_url: str = ""
    models: list = field(default_factory=list)

    @property
    def name(self):
        return "primary" if self.slot == 0 else f"fallback_{self.slot}"

    @property
    def protocol(self):
        url = (self.api_url or "").lower()
        if not url:
            return "gemini"
        if "/messages" in url:
            return "anthropic"
        if "/responses" in url:
            return "responses"
        return "openai"


def _parse_csv(value: str) -> list:
    """Parse comma-separated value, deduped + stripped."""
    if not value or not value.strip():
        return []
    seen = []
    for x in value.split(","):
        x = x.strip()
        if x and x not in seen:
            seen.append(x)
    return seen


def _build_providers() -> list:
    """Build LLM providers from LLM_* env vars (slots 0-9)."""
    providers = []
    for slot in range(10):
        suffix = "" if slot == 0 else f"_{slot}"

        api_key = os.getenv(f"LLM_API_KEY{suffix}", "").strip()
        api_keys = _parse_csv(os.getenv(f"LLM_API_KEYS{suffix}", ""))

        # Merge single key into keys list (deduped)
        if api_key and api_key not in api_keys:
            api_keys.insert(0, api_key)

        api_url = os.getenv(f"LLM_API_URL{suffix}", "").strip()
        models = _parse_csv(os.getenv(f"LLM_MODELS{suffix}", ""))

        # A slot is valid only if it has at least one key AND one model.
        # (Gemini slots may have empty api_url — that's the SDK signal.)
        if api_keys and models:
            providers.append(LLMProvider(
                slot=slot, api_key=api_key, api_keys=api_keys,
                api_url=api_url, models=models,
            ))

    return providers


LLM_PROVIDERS = _build_providers()
LLM_PROVIDER_COUNT = len(LLM_PROVIDERS)

# AI retry config (per-slot attempts).
# Prioritas: env AI_MAX_RETRIES > config.yaml ai.max_retries > default 2.
# Selalu di-clamp [1,10] supaya nilai liar (mis. 999) ga bikin loop ga wajar.
_ai_yaml = _c.get("ai", {})
try:
    AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", _ai_yaml.get("max_retries", 2)))
except (ValueError, TypeError):
    AI_MAX_RETRIES = 2
AI_MAX_RETRIES = max(1, min(AI_MAX_RETRIES, 10))


class Config:
    WIKI_LANG = _c.get("wikipedia", {}).get("lang", "id")

    # ── LLM Providers (slot-based) ──
    LLM_PROVIDERS = LLM_PROVIDERS
    LLM_PROVIDER_COUNT = LLM_PROVIDER_COUNT
    AI_MAX_RETRIES = AI_MAX_RETRIES

    @classmethod
    def get_all_providers(cls):
        """Return all configured LLM providers (primary first, then fallbacks).

        Slots auto-skip when they have no key+model, so this is already the
        usable set. Empty list = nothing configured (storyteller will raise a
        clear 'no provider' error instead of looping over phantom keys).
        """
        return cls.LLM_PROVIDERS

    # Convenience: primary slot's first model (for display only)
    @classmethod
    def primary_model(cls):
        if cls.LLM_PROVIDERS and cls.LLM_PROVIDERS[0].models:
            return cls.LLM_PROVIDERS[0].models[0]
        return "(none configured)"

    FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
    FB_PAGE_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    FB_APP_ID = os.getenv("FB_APP_ID", "")
    FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")
    FB_API_VERSION = _c.get("facebook", {}).get("api_version", "v21.0")
    SCHEDULE_MODE = _c.get("schedule", {}).get("mode", "fixed")
    INTERVAL_HOURS = _c.get("schedule", {}).get("interval_hours", 4)
    START_HOUR = _c.get("schedule", {}).get("start_hour", 8)
    _fixed_times = _c.get("schedule", {}).get("times", ["09:00", "19:00"])
    POST_TIMES = list(_fixed_times)  # resolved after class def via compute_post_times()
    TIMEZONE = _c.get("schedule", {}).get("timezone", "Asia/Jakarta")
    DATA_DIR = os.path.join(BASE_DIR, "data")
    SCRAPED_DIR = os.path.join(DATA_DIR, "scraped")
    STORIES_DIR = os.path.join(DATA_DIR, "stories")
    DB_PATH = os.path.join(DATA_DIR, "pipeline.db")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    MAX_RETRIES = _c.get("publish", {}).get("max_retries", 3)
    MAX_CHARS = _c.get("publish", {}).get("max_chars", 35000)

    # ── Story generation (narasi length tuning) ──
    _story = _c.get("story", {})
    STORY_MIN_CHARS = _story.get("min_chars", 16000)
    STORY_TARGET_MIN = _story.get("target_min", 18000)
    STORY_TARGET_MAX = _story.get("target_max", 19500)
    STORY_MAX_TOKENS = _story.get("max_tokens", 25000)
    # Kalau body < min_chars, sambung otomatis (bukan re-generate dari nol)
    STORY_AUTO_CONTINUE = _story.get("auto_continue", True)
    STORY_MAX_CONTINUATIONS = _story.get("max_continuations", 2)

    # ── LLM retry / rate-limit resilience ──
    _ai = _c.get("ai", {})
    # AI_MAX_RETRIES sudah di-resolve + clamp [1,10] di module-level (env>yaml>2).
    AI_MAX_RETRIES = AI_MAX_RETRIES
    # Retry khusus rate-limit (429) di slot yang sama sebelum pindah slot
    AI_RATELIMIT_RETRIES = _ai.get("ratelimit_retries", 4)
    AI_RATELIMIT_BACKOFF = _ai.get("ratelimit_backoff", 8)   # detik, base
    AI_RATELIMIT_BACKOFF_MAX = _ai.get("ratelimit_backoff_max", 60)  # cap

    # ── Auto-Generate ──
    STOCK_MIN = _c.get("auto_generate", {}).get("stock_min", 5)
    BATCH_SIZE = _c.get("auto_generate", {}).get("batch_size", 3)

    # ── Rest Hours ──
    REST_START = _c.get("schedule", {}).get("rest_start", 22)
    REST_END = _c.get("schedule", {}).get("rest_end", 6)

    # ── Telegram ──
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    @classmethod
    def compute_post_times(cls):
        """Return the effective list of post times (HH:MM) for the active mode.

        - fixed:    use the explicit `times` list from config.
        - interval: generate slots every INTERVAL_HOURS starting at START_HOUR,
                    wrapping within a 24h day, skipping rest hours.
        """
        if cls.SCHEDULE_MODE == "interval":
            try:
                step = max(1, min(int(cls.INTERVAL_HOURS), 24))
            except (ValueError, TypeError):
                step = 4
            try:
                start = int(cls.START_HOUR) % 24
            except (ValueError, TypeError):
                start = 8
            slots = []
            h = start
            # walk 24h worth of slots from start_hour
            for _ in range(24 // step + 1):
                if h >= 24:
                    break
                # skip rest hours
                in_rest = (h >= cls.REST_START or h < cls.REST_END)
                if not in_rest:
                    slots.append(f"{h:02d}:00")
                h += step
            # fallback: if everything fell in rest hours, at least post at start
            return slots or [f"{start:02d}:00"]
        # fixed mode
        return list(cls._fixed_times)


# POST_TIMES resolved once at import (daemon reads fresh on each start).
Config.POST_TIMES = Config.compute_post_times()
config = Config()
