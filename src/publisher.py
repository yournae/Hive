import logging, requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .config import config
GRAPH = "https://graph.facebook.com/" + config.FB_API_VERSION
log = logging.getLogger(__name__)

class TokenError(Exception): pass
class TransientError(Exception): pass

# Cache resolved page token (may differ from user token)
_page_token = None

def invalidate_page_token():
    """Clear cached page token so next call re-resolves it."""
    global _page_token
    _page_token = None
    log.info("Page token cache invalidated")

def resolve_page_token():
    """Auto-resolve Page Access Token from User Access Token if needed."""
    global _page_token
    if _page_token:
        return _page_token
    token = config.FB_PAGE_TOKEN
    if not token:
        raise TokenError("FB_PAGE_ACCESS_TOKEN kosong")
    # Check token type via debug_token
    try:
        r = requests.get(GRAPH + "/debug_token",
            params={"input_token": token, "access_token": token}, timeout=15)
        data = r.json().get("data", {})
        if not data.get("is_valid"):
            raise TokenError("Token tidak valid/kadaluarsa: " + str(data.get("error")))
    except TokenError:
        raise
    except Exception as e:
        raise TokenError("Gagal validasi token: " + str(e))
    # If it's a user token, resolve page token via /me/accounts
    if data.get("type", "").lower() == "user":
        log.info("Token type: USER → auto-resolving Page Access Token...")
        r = requests.get(GRAPH + "/me/accounts",
            params={"fields": "id,name,access_token", "access_token": token}, timeout=15)
        pages = r.json().get("data", [])
        for p in pages:
            if str(p["id"]) == str(config.FB_PAGE_ID):
                _page_token = p["access_token"]
                log.info(f"✅ Resolved page token for '{p.get('name')}' (ID: {p['id']})")
                return _page_token
        raise TokenError(
            f"Page ID {config.FB_PAGE_ID} tidak ditemukan di /me/accounts. "
            f"Pastikan token punya akses ke page tersebut."
        )
    else:
        log.info(f"Token type: {data.get('type', 'unknown')} (langsung pakai)")
        _page_token = token
        return _page_token

def validate_token():
    if not config.FB_PAGE_TOKEN: raise TokenError("FB_PAGE_ACCESS_TOKEN kosong")
    r = requests.get(GRAPH + "/debug_token",
        params={"input_token":config.FB_PAGE_TOKEN,"access_token":config.FB_PAGE_TOKEN}, timeout=30)
    data = r.json().get("data", {})
    if not data.get("is_valid"):
        raise TokenError("Token tidak valid/kadaluarsa: " + str(data.get("error")))
    return data

def get_long_lived_token(short_token):
    if not (config.FB_APP_ID and config.FB_APP_SECRET):
        raise TokenError("FB_APP_ID/FB_APP_SECRET dibutuhkan untuk refresh token")
    r = requests.get(GRAPH + "/oauth/access_token", params={
        "grant_type":"fb_exchange_token","client_id":config.FB_APP_ID,
        "client_secret":config.FB_APP_SECRET,"fb_exchange_token":short_token}, timeout=30)
    r.raise_for_status(); return r.json().get("access_token")

@retry(reraise=True, stop=stop_after_attempt(config.MAX_RETRIES),
       wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception_type(TransientError))
def publish_post(message):
    page_token = resolve_page_token()
    msg = message
    if len(msg) > config.MAX_CHARS:
        # Boundary-aware truncation: paragraph > sentence > word > hard cut
        truncated = msg[:config.MAX_CHARS]
        for delim in ('\n\n', '\n', '. ', ' '):
            idx = truncated.rfind(delim)
            if idx > config.MAX_CHARS * 0.75:
                msg = truncated[:idx].strip()
                if delim in ('. ', ' '):
                    msg += '.'
                break
        else:
            msg = truncated.rstrip() + '…'
        log.warning("Message truncated for publish: %d → %d chars", len(message), len(msg))
    r = requests.post("%s/%s/feed" % (GRAPH, config.FB_PAGE_ID),
        data={"message":msg,"access_token":page_token}, timeout=60)
    if r.status_code >= 500 or r.status_code == 429:
        raise TransientError("HTTP %s: %s" % (r.status_code, r.text))
    j = r.json()
    if "error" in j:
        e = j["error"]
        if e.get("code") == 190:
            invalidate_page_token()
            raise TokenError(e.get("message"))
        if e.get("is_transient"): raise TransientError(e.get("message"))
        raise RuntimeError("FB error: " + str(e))
    pid = j.get("id")
    url = ("https://www.facebook.com/" + pid.replace("_", "/posts/", 1)) if pid and "_" in pid else None
    return pid, url
