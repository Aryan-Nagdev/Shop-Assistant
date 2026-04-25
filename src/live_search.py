"""
live_search.py  –  Live Product Search
───────────────────────────────────────
Fixes:
  1. Price handling — ₹99 no longer treated as USD
  2. Comparison deduplication — same product won't appear on both sides
  3. Retry logic — retries once on timeout
  4. Graceful empty fallback — returns [] with a log, never crashes
  5. Rank scoring — cleaner, no division-by-zero
"""
import os, re, sys, time, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SERPAPI_URL     = "https://serpapi.com/search.json"
SCRAPINGDOG_URL = "https://api.scrapingdog.com/google_shopping"


# ── Currency helpers ───────────────────────────────────────────────────────────
def _parse_num(raw) -> float | None:
    if raw is None:
        return None
    s = re.sub(r'[^\d\.]', '', str(raw))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def to_inr(price_raw) -> str:
    """Convert any price to a ₹ INR display string."""
    if not price_raw:
        return 'Price not available'
    s = str(price_raw).strip()

    # Already in INR
    if re.match(r'^[₹₨]|^Rs\.?\s*\d|^INR', s, re.I):
        num = _parse_num(s)
        return f"₹{num:,.0f}" if num else s

    # USD
    if '$' in s:
        num = _parse_num(s)
        return f"₹{num * config.USD_TO_INR:,.0f}" if num else s

    # Bare number — assume INR (we get Indian results so this is almost always INR)
    # Only treat as USD if number is very small (<10) and looks like a dollar amount
    num = _parse_num(s)
    if num is not None:
        if num < 10:
            return f"₹{num * config.USD_TO_INR:,.0f}"
        return f"₹{num:,.0f}"

    return s


def _numeric_inr(price_raw) -> float:
    """Return numeric INR value for price filtering."""
    s = str(price_raw or '')
    num = _parse_num(s)
    if num is None:
        return 0.0
    if '$' in s:
        return num * config.USD_TO_INR
    if num < 10:
        return num * config.USD_TO_INR
    return num


# ── Link validator ─────────────────────────────────────────────────────────────
def _valid_link(url) -> str | None:
    if not url:
        return None
    u = str(url).strip()
    return u if u.startswith(('http://', 'https://')) else None


def _fallback_link(title: str) -> str:
    """Flipkart search as reliable fallback."""
    return f"https://www.flipkart.com/search?q={requests.utils.quote(title or 'product')}"


# ── HTTP with retry ────────────────────────────────────────────────────────────
def _get(url: str, params: dict, retries: int = 1, timeout: int = 12):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            if attempt < retries:
                print(f"[Search] Timeout — retrying ({attempt + 1}/{retries})...")
                time.sleep(1)
            else:
                raise
        except Exception:
            raise
    return None


# ── SerpAPI ────────────────────────────────────────────────────────────────────
def _serpapi(query: str, num: int = 8) -> list[dict]:
    if not config.SERPAPI_KEY:
        print("[SerpAPI] No API key configured.")
        return []

    params = {
        'engine':   'google_shopping',
        'q':        query,
        'api_key':  config.SERPAPI_KEY,
        'num':      num,
        'gl':       config.COUNTRY,
        'hl':       config.LANGUAGE,
        'location': 'India',
    }
    try:
        r = _get(SERPAPI_URL, params)
        items = r.json().get('shopping_results', [])
        return [_normalize(it, query) for it in items]
    except Exception as e:
        print(f"[SerpAPI] Error: {e}")
        return []


# ── ScrapingDog fallback ───────────────────────────────────────────────────────
def _scrapingdog(query: str, num: int = 8) -> list[dict]:
    if not config.SCRAPINGDOG_KEY:
        print("[ScrapingDog] No API key configured.")
        return []

    params = {
        'api_key': config.SCRAPINGDOG_KEY,
        'query':   query,
        'results': num,
        'country': 'IN',
    }
    try:
        r = _get(SCRAPINGDOG_URL, params)
        items = r.json().get('shopping_results', [])
        return [_normalize(it, query) for it in items]
    except Exception as e:
        print(f"[ScrapingDog] Error: {e}")
        return []


def _normalize(it: dict, fallback_query: str) -> dict:
    """Normalise a raw API result into a clean product dict."""
    title     = it.get('title', '')
    price_raw = it.get('price') or it.get('extracted_price')
    link      = (_valid_link(it.get('link'))
                 or _valid_link(it.get('product_link'))
                 or _fallback_link(title or fallback_query))
    return {
        'title':     title,
        'price_inr': to_inr(price_raw),
        'price_num': _numeric_inr(price_raw),
        'rating':    it.get('rating'),
        'reviews':   it.get('reviews'),
        'source':    it.get('source', ''),
        'link':      link,
        'thumbnail': it.get('thumbnail', ''),
        'brand':     it.get('brand', ''),
    }


# ── Ranking ────────────────────────────────────────────────────────────────────
_INDIAN_DOMAINS = {d.split('.')[0] for d in config.INDIAN_DOMAINS}
_INDIAN_BRANDS  = {b.lower() for blist in config.INDIAN_BRANDS.values() for b in blist}


def _rank(products: list[dict], ents: dict, max_price: int | None) -> list[dict]:
    want_brands = [b.lower() for b in ents.get('brands', [])]
    want_colors = ents.get('colors', [])

    scored = []
    for p in products:
        # Hard price filter with 8% tolerance
        if max_price and p['price_num'] > 0:
            if p['price_num'] > max_price * 1.08:
                continue

        t = p['title'].lower()
        s = 0.0

        # Wanted brands
        for b in want_brands:
            if re.search(r'\b' + re.escape(b) + r'\b', t):
                s += 4.0

        # Indian brand bonus
        for b in _INDIAN_BRANDS:
            if re.search(r'\b' + re.escape(b) + r'\b', t):
                s += 1.0
                break

        # Color match
        for c in want_colors:
            if re.search(r'\b' + re.escape(c) + r'\b', t):
                s += 2.0

        # Rating bonus (safe cast)
        try:
            s += float(p.get('rating') or 0) * 0.4
        except (TypeError, ValueError):
            pass

        # Indian domain bonus
        src = p.get('source', '').lower()
        for dom in _INDIAN_DOMAINS:
            if dom in src:
                s += 2.5
                break

        p['_score'] = s
        scored.append(p)

    scored.sort(key=lambda x: x.get('_score', 0), reverse=True)
    return scored


# ── Public API ─────────────────────────────────────────────────────────────────
def fetch_one(query: str, ents: dict, top_n: int = 6) -> list[dict]:
    """Fetch, rank and return top_n products for a single query."""
    raw = _serpapi(query, num=top_n * 3)
    if not raw:
        print(f"[Search] SerpAPI returned nothing for '{query}', trying ScrapingDog...")
        raw = _scrapingdog(query, num=top_n * 3)
    if not raw:
        print(f"[Search] Both APIs returned nothing for '{query}'.")
        return []

    ranked = _rank(raw, ents, ents.get('max_price'))
    return ranked[:top_n]


def fetch_comparison(queries: list[dict], ents: dict, per_brand: int = 3) -> dict[str, list]:
    """
    Fetch per_brand products for each brand query separately.
    Deduplicates across brands so the same product doesn't appear twice.
    Returns {label: [products]}.
    """
    result: dict[str, list] = {}
    seen_links: set[str] = set()

    for q_info in queries:
        label = q_info['label']
        query = q_info['query']

        raw = _serpapi(query, num=per_brand * 4)
        if not raw:
            raw = _scrapingdog(query, num=per_brand * 4)

        ranked = _rank(raw, ents, ents.get('max_price'))

        # Deduplicate across brands
        unique = []
        for p in ranked:
            link = p.get('link', '')
            if link not in seen_links:
                seen_links.add(link)
                unique.append(p)
            if len(unique) >= per_brand:
                break

        result[label] = unique

    return result
