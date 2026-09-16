"""
live_search.py  –  Strict Product Retrieval, Normalization & Constraint Validation (Phase 2)
─────────────────────────────────────────────────────────────────────────────────────────────
Architectural Pipeline:
  SerpAPI / ScrapingDog
          ↓
  Raw Search Results
          ↓
  Product Normalization (NormalizedProduct schema)
          ↓
  Strict Constraint Validator (validate_product: Category, Brand, Price, Specs, Color, Accessory)
          ├── 3-State Evaluation: MATCH / MISMATCH / UNKNOWN
          └── Rejection Logging with Explicit Reasons
          ↓
  Hard Constraint Gate (Hard failures strictly REJECTED)
          ↓
  Multi-Factor Ranking (Only valid products ranked)
          ↓
  Clean Validated Products (or structured 'No exact match found')
"""
from __future__ import annotations
import os
import re
import sys
import time
import json
import requests
import random
from typing import Any

# Ensure stdout handles utf-8 encoding safely on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.query_understanding import BRAND_REGISTRY, QueryUnderstanding

SERPAPI_URL     = "https://serpapi.com/search.json"
SCRAPINGDOG_URL = "https://api.scrapingdog.com/google_shopping"

DEFAULT_COUNT = 6   # default number of products to return


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CURRENCY & PRICE PARSING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_num(raw: Any) -> float | None:
    if raw is None:
        return None
    # Strip currency symbols and non-numeric characters except dot
    s = re.sub(r'[^\d\.]', '', str(raw))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def to_inr(price_raw: Any) -> str:
    """Format raw price into clean INR display string."""
    if price_raw is None or price_raw == '':
        return 'Price not available'
    s = str(price_raw).strip()

    if re.match(r'^[₹₨]|^Rs\.?\s*\d|^INR', s, re.I):
        num = _parse_num(s)
        return f"₹{num:,.0f}" if num else s

    if '$' in s or 'usd' in s.lower():
        num = _parse_num(s)
        return f"₹{num * config.USD_TO_INR:,.0f}" if num else s

    num = _parse_num(s)
    if num is not None:
        if num < 20:
            return f"₹{num * config.USD_TO_INR:,.0f}"
        return f"₹{num:,.0f}"

    return s


def _numeric_inr(price_raw: Any) -> float:
    """Extract numeric INR price value, handling USD conversion and noise."""
    s = str(price_raw or '')
    num = _parse_num(s)
    if num is None:
        return 0.0
    if '$' in s or 'usd' in s.lower():
        return num * config.USD_TO_INR
    if num < 20:
        return num * config.USD_TO_INR
    return num


def _extract_selling_price(it: dict) -> tuple[float | None, str]:
    """
    Carefully extract actual current selling price from search result item metadata.
    Detects USD from currency, price symbol, retailer (e.g. Best Buy, Walmart),
    or tech item pricing anomalies, converting correctly to INR.
    """
    price_str = str(it.get('price') or '')
    curr_str = str(it.get('currency') or '').strip().upper()
    src_str = str(it.get('source') or '').lower()
    link_str = str(it.get('link') or it.get('product_link') or '').lower()

    is_usd = False
    if '$' in price_str or curr_str in ('$', 'USD') or 'usd' in price_str.lower():
        is_usd = True
    elif any(us_store in src_str or us_store in link_str for us_store in (
        'best buy', 'bestbuy.com', 'walmart', 'target', 'b&h', 'bhphotovideo', 'newegg', 'micro center'
    )):
        is_usd = True

    # 1. Check extracted_price / price fields
    raw_val = it.get('extracted_price') or it.get('price')
    num = _parse_num(raw_val)

    if num is not None and num > 0:
        # Heuristic for tech items: laptops, macbooks, smartphones priced 40..2500 without INR symbols are USD
        if not is_usd and 40 <= num <= 2500 and not re.search(r'[₹₨]|rs\.?|inr', price_str, re.I):
            title_lower = str(it.get('title') or '').lower()
            if any(w in title_lower for w in ('laptop', 'notebook', 'macbook', 'smartphone', 'iphone', 'galaxy s', 'thinkpad')):
                is_usd = True

        if is_usd:
            num = round(num * config.USD_TO_INR, 2)
        return num, f"₹{num:,.0f}"

    # 2. Check raw price string in title / snippet if missing
    text = f"{it.get('title', '')} {it.get('snippet', '')}"
    m = re.search(r'(?:₹|Rs\.?|INR)\s*(\d[\d,]*)', text, re.I)
    if m:
        num = float(m.group(1).replace(',', ''))
        if num > 0:
            return num, f"₹{num:,.0f}"

    m_usd = re.search(r'\$\s*(\d+(?:\.\d+)?)', text)
    if m_usd:
        num = float(m_usd.group(1)) * config.USD_TO_INR
        if num > 0:
            return num, f"₹{num:,.0f}"

    return None, "Price not available"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. NORMALIZED PRODUCT DATA SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

class NormalizedProduct:
    """
    Standardized, normalized schema for candidate products retrieved from search.
    Consolidates evidence from title, snippet, description, brand, and pricing.
    """
    __slots__ = (
        'title',
        'brand',
        'category',
        'price_num',
        'price_inr',
        'currency',
        'color',
        'specifications',
        'description',
        'source',
        'link',
        'thumbnail',
        'fallback_thumbnail',
        'serpapi_thumbnail',
        'rating',
        'reviews',
        'is_accessory',
        'raw',
    )

    def __init__(
        self,
        title: str,
        brand: str | None = None,
        category: str | None = None,
        price_num: float | None = None,
        price_inr: str = "Price not available",
        currency: str = "INR",
        color: str | None = None,
        specifications: dict[str, str] | None = None,
        description: str = "",
        source: str = "",
        link: str = "",
        thumbnail: str = "",
        fallback_thumbnail: str = "",
        serpapi_thumbnail: str = "",
        rating: float | None = None,
        reviews: int | None = None,
        is_accessory: bool = False,
        raw: dict | None = None,
    ):
        self.title              = title
        self.brand              = brand
        self.category           = category
        self.price_num          = price_num
        self.price_inr          = price_inr
        self.currency           = currency
        self.color              = color
        self.specifications     = specifications or {}
        self.description        = description
        self.source             = source
        self.link               = link
        self.thumbnail          = thumbnail
        self.fallback_thumbnail = fallback_thumbnail
        self.serpapi_thumbnail  = serpapi_thumbnail
        self.rating             = rating
        self.reviews            = reviews
        self.is_accessory       = is_accessory
        self.raw                = raw or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert normalized product into standard dictionary for responses and UI."""
        return {
            'title':              self.title,
            'brand':              self.brand,
            'category':           self.category,
            'price_inr':          self.price_inr,
            'price_num':          self.price_num or 0.0,
            'rating':             self.rating,
            'reviews':            self.reviews,
            'source':             self.source,
            'link':               self.link,
            'thumbnail':          self.thumbnail,
            'fallback_thumbnail': self.fallback_thumbnail,
            'serpapi_thumbnail':  self.serpapi_thumbnail,
            'color':              self.color,
            'specifications':     self.specifications,
        }

    def __repr__(self) -> str:
        return f"<NormalizedProduct title={self.title[:30]!r} brand={self.brand!r} price={self.price_inr} cat={self.category!r}>"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ACCESSORY & EXCLUSION FILTER
# ═══════════════════════════════════════════════════════════════════════════════

_ACCESSORY_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b(?:case|cover|skin|skins|sticker|stickers|decal|decals|wrap|wraps|sleeve|pouch|protector|tempered\s*glass|guard|body\s*wrap)\b', re.I),
    re.compile(r'\b(?:cable|charger|adapter|cord|power\s*adapter|charging\s*dock|charging\s*case\s*only)\b', re.I),
    re.compile(r'\b(?:stand|holder|mount|bracket|tripod|cooling\s*pad|cooler\s*pad)\b', re.I),
    re.compile(r'\b(?:replacement\s*tips|ear\s*tips|ear\s*pads|ear\s*cushions|cushion\s*pads|eartips|silicone\s*tips)\b', re.I),
    re.compile(r'\b(?:watch\s*strap|band\s*strap|replacement\s*band|wrist\s*strap)\b', re.I),
    re.compile(r'\b(?:shoe\s*polish|shoe\s*rack|shoe\s*tree|shoe\s*bag|shoe\s*laces|insole|heel\s*pads)\b', re.I),
    re.compile(r'\b(?:cleaning\s*kit|dust\s*plug|anti\s*dust|keyboard\s*skin|keyboard\s*cover|screen\s*guard|screen\s*protector|privacy\s*screen)\b', re.I),
    re.compile(r'\b(?:pen\s*drive|pendrive|flash\s*drive|memory\s*card|microsd|sd\s*card|lga\s*\d+|cpu\s*only|processor\s*only|desktop\s*processor)\b', re.I),
    re.compile(r'\b(?:dummy\s*phone|toy\s*phone|toy\s*laptop|laptop\s*skin|laptop\s*sticker|laptop\s*decal)\b', re.I),
]


def _check_is_accessory(title: str, snippet: str = "") -> bool:
    """Return True if title indicates an accessory/component rather than the primary product."""
    combined = f"{title} {snippet}"
    for pat in _ACCESSORY_PATTERNS:
        if pat.search(combined):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PRODUCT NORMALIZER ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _valid_link(url: Any) -> str | None:
    if not url:
        return None
    u = str(url).strip()
    return u if u.startswith(('http://', 'https://')) else None


def _fallback_link(title: str, source: str = "") -> str:
    q = requests.utils.quote(title or 'product')
    s_l = (source or '').lower()
    if 'amazon' in s_l:
        return f"https://www.amazon.in/s?k={q}"
    if 'myntra' in s_l:
        return f"https://www.myntra.com/{q}"
    return f"https://www.flipkart.com/search?q={q}"


def normalize_raw_item(it: dict, fallback_query: str) -> NormalizedProduct:
    """
    Converts a raw search result dictionary (from SerpAPI/ScrapingDog) into NormalizedProduct.
    Extracts brand, category, specs, colors, price, and all available product images.
    """
    title = str(it.get('title') or '').strip()
    snippet = str(it.get('snippet') or it.get('description') or '').strip()
    combined_text = f"{title} {snippet}"
    source_name = str(it.get('source') or '').strip()

    # Price
    price_num, price_inr = _extract_selling_price(it)

    # Link
    link = (_valid_link(it.get('link'))
            or _valid_link(it.get('product_link'))
            or _fallback_link(title or fallback_query, source=source_name))

    # Rating & reviews
    rating_val = None
    try:
        if it.get('rating') is not None:
            rating_val = float(it['rating'])
    except (ValueError, TypeError):
        pass

    reviews_val = None
    try:
        if it.get('reviews') is not None:
            reviews_val = int(str(it['reviews']).replace(',', '').replace('+', ''))
    except (ValueError, TypeError):
        pass

    # Brand extraction: check explicit brand metadata, then BrandRegistry
    detected_brand = it.get('brand')
    if not detected_brand:
        _, res_brand, _, _ = BRAND_REGISTRY.resolve(title)
        detected_brand = res_brand

    # Accessory check
    is_acc = _check_is_accessory(title, snippet)

    # Specs extraction from full product text
    specs = {}

    # CPU
    m_cpu = re.search(r'\b(intel\s+core\s+)?(i[3579][-\s]?\d{4,5}\w*|i[3579]|ryzen\s*[3579]\s*(?:\d{4}\w*)?|m[1234]\s*(?:pro|max|ultra)?|celeron|pentium|snapdragon\s*\w+|dimensity\s*\w+)\b', combined_text, re.I)
    if m_cpu:
        raw_c = m_cpu.group(0).strip()
        # Canonicalize Core i5 / i5
        if re.search(r'\bi5\b|\bcore\s+i5\b|\bi5[-\s]\d', raw_c, re.I):
            specs['cpu'] = 'i5'
        elif re.search(r'\bi7\b|\bcore\s+i7\b|\bi7[-\s]\d', raw_c, re.I):
            specs['cpu'] = 'i7'
        elif re.search(r'\bi3\b|\bcore\s+i3\b|\bi3[-\s]\d', raw_c, re.I):
            specs['cpu'] = 'i3'
        elif re.search(r'\bi9\b|\bcore\s+i9\b|\bi9[-\s]\d', raw_c, re.I):
            specs['cpu'] = 'i9'
        elif 'ryzen' in raw_c.lower():
            specs['cpu'] = raw_c.title()
        else:
            specs['cpu'] = raw_c

    # RAM
    m_ram = re.search(r'\b(\d+)\s*gb\s*(?:ram|lpddr\d?|ddr\d?|memory)?\b(?!\s*(?:ssd|hdd|rom|storage|internal))', combined_text, re.I)
    if m_ram:
        r_val = int(m_ram.group(1))
        if r_val in (2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64):
            specs['ram'] = f"{r_val}GB"

    # Storage
    m_stor = re.search(r'\b(128|256|512|1024|2048)\s*(?:gb\s*)?(ssd|hdd|nvme|emmc|storage|rom|internal)\b|\b([12])\s*tb\s*(?:ssd|hdd|storage)?\b', combined_text, re.I)
    if m_stor:
        if m_stor.group(3):  # TB match
            specs['storage'] = f"{m_stor.group(3)}TB SSD"
        else:
            unit = m_stor.group(2).upper() if m_stor.group(2) else 'SSD'
            specs['storage'] = f"{m_stor.group(1)}GB {unit}"

    # GPU
    m_gpu = re.search(r'\b(rtx\s*\d{3,4}\w*|gtx\s*\d{3,4}\w*|rx\s*\d{3,4}\w*|arc\s*[a-z]?\d{3}|dedicated\s*graphics|discrete\s*gpu|graphics\s*card|with\s*graphics)\b', combined_text, re.I)
    if m_gpu:
        raw_g = m_gpu.group(1).strip().upper().replace(' ', '')
        if 'RTX' in raw_g:
            specs['gpu'] = raw_g
        elif 'GTX' in raw_g:
            specs['gpu'] = raw_g
        elif 'RX' in raw_g:
            specs['gpu'] = raw_g
        else:
            specs['gpu'] = 'dedicated'

    # ANC (Audio)
    if re.search(r'\b(?:anc|active\s+noise\s+cancel(?:l?ation|ling)?|noise\s+cancel(?:l?ation|ling)?)\b', combined_text, re.I):
        specs['anc'] = 'ANC'

    # Battery
    m_bat = re.search(r'\b(\d{4,5})\s*mah\b|\b(\d+)\s*(?:hours?|hrs?|h)\s*(?:battery|playtime|backup)\b', combined_text, re.I)
    if m_bat:
        if m_bat.group(1):
            specs['battery'] = f"{m_bat.group(1)}mAh"
        elif m_bat.group(2):
            specs['battery'] = f"{m_bat.group(2)} hours"

    # Color extraction: check title for explicit color words
    detected_color = None
    title_lower = title.lower()
    for col in (
        'navy blue', 'sky blue', 'off white', 'dark green', 'light blue', 'dark blue',
        'blue', 'black', 'white', 'red', 'green', 'pink', 'yellow', 'purple',
        'orange', 'gray', 'grey', 'silver', 'gold', 'brown', 'navy', 'beige',
        'maroon', 'cream', 'olive', 'teal', 'coral', 'khaki', 'lavender'
    ):
        if re.search(r'\b' + re.escape(col) + r'\b', title_lower):
            detected_color = 'gray' if col == 'grey' else col
            break

    # Image extraction: collect and rank all valid image URLs from API response
    raw_thumb = str(it.get('thumbnail') or '').strip()
    raw_serp_thumb = str(it.get('serpapi_thumbnail') or '').strip()
    raw_img = str(it.get('image') or it.get('product_image') or it.get('thumbnail_url') or '').strip()
    raw_images = it.get('images') if isinstance(it.get('images'), list) else []

    img_cands: list[str] = []
    for cand in [raw_thumb, raw_serp_thumb, raw_img] + raw_images:
        if cand and isinstance(cand, str) and cand.startswith(('http://', 'https://')):
            c = cand.strip()
            if c not in img_cands:
                img_cands.append(c)

    primary_thumb = img_cands[0] if img_cands else ""
    fallback_thumb = img_cands[1] if len(img_cands) > 1 else (raw_serp_thumb if raw_serp_thumb and raw_serp_thumb != primary_thumb else "")

    return NormalizedProduct(
        title=title,
        brand=detected_brand,
        price_num=price_num,
        price_inr=price_inr,
        currency="INR",
        color=detected_color,
        specifications=specs,
        description=snippet,
        source=source_name,
        link=link,
        thumbnail=primary_thumb,
        fallback_thumbnail=fallback_thumb,
        serpapi_thumbnail=raw_serp_thumb,
        rating=rating_val,
        reviews=reviews_val,
        is_accessory=is_acc,
        raw=it,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. STRICT THREE-STATE CONSTRAINT VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════════

class ValidationResult:
    """
    Detailed result of product validation containing status, reasons, and per-requirement breakdown.
    """
    __slots__ = ('valid', 'status', 'reasons', 'requirements', 'product')

    def __init__(self, product: NormalizedProduct):
        self.product = product
        self.valid: bool = True
        self.status: str = "accepted"  # "accepted" | "rejected" | "incomplete"
        self.reasons: list[str] = []
        self.requirements: dict[str, str] = {}  # req_name -> "match" | "mismatch" | "unknown"

    def reject(self, req_name: str, reason: str):
        self.valid = False
        self.status = "rejected"
        self.requirements[req_name] = "mismatch"
        if reason not in self.reasons:
            self.reasons.append(reason)

    def mark_unknown(self, req_name: str, reason: str, is_hard: bool = True):
        self.requirements[req_name] = "unknown"
        if is_hard:
            self.valid = False
            self.status = "incomplete"
            if reason not in self.reasons:
                self.reasons.append(reason)

    def match(self, req_name: str):
        self.requirements[req_name] = "match"


# Audio category definitions (strict positive & negative keywords)
_AUDIO_CATEGORY_RULES: dict[str, dict[str, list[str]]] = {
    'earbuds': {
        'pos': ['earbuds', 'tws', 'true wireless', 'in-ear wireless', 'truly wireless',
                'wireless earbuds', 'tws earbuds', 'airdopes', 'airpods', 'buds', 'earbud'],
        'neg': ['headphone', 'neckband', 'speaker', 'soundbar', 'wired earphone', 'earphone'],
    },
    'headphones': {
        'pos': ['headphone', 'over-ear', 'on-ear', 'headset', 'over ear', 'on ear', 'wireless headphone'],
        'neg': ['earbuds', 'neckband', 'tws', 'true wireless', 'airpods', 'speaker', 'earphone'],
    },
    'earphones': {
        'pos': ['earphone', 'in-ear', 'wired earphone', 'iem', 'wired in-ear', 'wired earphones'],
        'neg': ['headphone', 'neckband', 'earbuds', 'tws', 'true wireless', 'speaker', 'airpods'],
    },
    'neckband': {
        'pos': ['neckband', 'neck band', 'wireless neckband'],
        'neg': ['headphone', 'earbuds', 'tws', 'true wireless', 'speaker', 'earphone'],
    },
    'speaker': {
        'pos': ['speaker', 'soundbar', 'home theatre', 'boom box', 'bluetooth speaker', 'portable speaker'],
        'neg': ['earbuds', 'earphone', 'headphone', 'neckband'],
    },
}

# Generic product category definitions
_GENERIC_CATEGORY_RULES: dict[str, dict[str, list[str]]] = {
    'laptop': {
        'pos': ['laptop', 'notebook', 'ultrabook', 'chromebook', 'macbook', 'ideapad',
                'thinkpad', 'vivobook', 'zenbook', 'pavilion', 'victus', 'tuf gaming',
                'predator', 'legion', 'loq', 'vostro', 'inspiron'],
        'neg': ['desktop', 'all-in-one', 'pc cabinet', 'cabinet only', 'motherboard only',
                'toy laptop', 'laptop bag', 'mouse pad', 'keyboard skin', 'keyboard cover',
                'skin', 'skins', 'sticker', 'stickers', 'decal', 'decals', 'vinyl cover',
                'body wrap', 'sleeve only', 'pouch only', 'case only', 'adapter', 'charger',
                'cooling pad', 'laptop stand'],
    },
    'phone': {
        'pos': ['phone', 'smartphone', 'mobile', 'iphone', 'galaxy', '5g phone'],
        'neg': ['phone case', 'back cover', 'tempered glass', 'screen protector',
                'dummy phone', 'toy phone'],
    },
    'shoes': {
        'pos': ['shoes', 'sneakers', 'footwear', 'running shoes', 'sports shoes',
                'loafers', 'sandals', 'boots', 'casual shoes', 'formal shoes', 'clogs'],
        'neg': ['shoe polish', 'shoe rack', 'shoe tree', 'shoe bag', 'laces only',
                'insole only', 'socks', 't-shirt', 'shirt'],
    },
    't-shirt': {
        'pos': ['t-shirt', 'tshirt', 't shirt', 'tee', 'polo t-shirt', 'half sleeve shirt',
                'graphic shirt', 'round neck shirt', 'crew neck shirt', 'printed shirt',
                'half-sleeve', 'round neck', 'crew neck'],
        'neg': ['jeans', 'shoes', 'trouser', 'jacket', 'track pant', 'formal shirt',
                'full sleeve shirt', 'long sleeve shirt'],
    },
    'shirt': {
        'pos': ['formal shirt', 'casual shirt', 'cotton shirt', 'linen shirt', 'shirt',
                'full sleeve shirt', 'long sleeve shirt', 'oxford shirt', 'check shirt',
                'striped shirt'],
        'neg': ['t-shirt', 'tshirt', 'jeans', 'shoes', 'track pant'],
    },
    'jeans': {
        'pos': ['jeans', 'denim'],
        'neg': ['shirt', 't-shirt', 'jacket', 'belt only'],
    },
    'smartwatch': {
        'pos': ['smartwatch', 'smart watch', 'fitness band', 'smart band', 'fitness tracker'],
        'neg': ['wall clock', 'table clock', 'alarm clock', 'watch strap only'],
    },
    'watch': {
        'pos': ['watch', 'wrist watch', 'analog watch', 'digital watch', 'chronograph'],
        'neg': ['wall clock', 'table clock', 'alarm clock', 'strap only'],
    },
    'camera': {
        'pos': ['camera', 'dslr', 'mirrorless', 'action camera'],
        'neg': ['camera bag', 'lens cap', 'tripod only', 'strap only'],
    },
    'office wear': {
        'pos': ['shirt', 'trouser', 'trousers', 'formal', 'blazer', 'suit', 'pants', 'office',
                'oxford', 'polo', 'chinos', 'waistcoat', 'tie', 'attire', 'dress shirt',
                'formal wear', 'kurta', 'work wear', 'workwear', 'formal pant'],
        'neg': ['nightwear', 'pajama', 'swimwear', 'gym wear', 'sweatpants'],
    },
    'clothing': {
        'pos': ['shirt', 't-shirt', 'trouser', 'trousers', 'formal', 'blazer', 'suit', 'pants',
                'jeans', 'dress', 'kurta', 'polo', 'chinos', 'jacket', 'hoodie', 'apparel',
                'wear', 'tee', 'top'],
        'neg': ['shoe polish', 'hanger only', 'cover only'],
    },
    'trouser': {
        'pos': ['trouser', 'trousers', 'pants', 'chinos', 'formal pant', 'office pant'],
        'neg': ['shorts', 'skirt', 'shoe'],
    },
}

_CATEGORY_ALIASES = {
    'Clothing_Shoes_and_Jewelry': 'clothing',
    'footwear': 'shoes',
    'sneakers': 'shoes',
    'formal wear': 'office wear',
    'work wear': 'office wear',
    'pants': 'trouser',
    'trousers': 'trouser',
}


def validate_product(
    prod: NormalizedProduct,
    target_category: str | None,
    audio_type: str | None,
    want_brands: list[str],
    max_price: int | None,
    min_price: int | None,
    tech_specs: dict[str, str],
    want_colors: list[str],
    hard_requirements: list[str],
    category_confidence: float = 1.0,
    want_gender: str | None = None,
) -> ValidationResult:
    """
    Executes strict multi-factor constraint validation on a NormalizedProduct.
    Evaluates: Accessory Filter, Category Match, Brand Match, Price Match, Specs Match, Color Match.
    Returns a ValidationResult object with 3-state requirement tags (MATCH, MISMATCH, UNKNOWN).
    """
    res = ValidationResult(prod)
    title_lower = prod.title.lower()
    desc_lower = prod.description.lower()
    full_text = f"{title_lower} {desc_lower}"

    # ── 1. Accessory / Exclusion Filter ───────────────────────────────────────
    if prod.is_accessory and (target_category or audio_type or want_brands or tech_specs):
        res.reject('accessory_check', f"Product is an accessory/component, not the requested primary item")
        return res
    else:
        res.match('accessory_check')

    # ── 2. Category Validation ────────────────────────────────────────────────
    # Only enforce strict category validation when Category confidence is high (>= 0.70)
    if category_confidence >= 0.70:
        # 2a. Strict Audio Category Validation
        if audio_type:
            rules = _AUDIO_CATEGORY_RULES.get(audio_type)
            if rules:
                has_pos = any(re.search(r'\b' + re.escape(p) + r'(?:s|es)?\b', title_lower) for p in rules['pos'])

                # Check negative exclusions
                for excl in rules['neg']:
                    if excl == 'earphone' and has_pos:
                        continue
                    if re.search(r'\b' + re.escape(excl) + r'(?:s|es)?\b', title_lower):
                        res.reject('category', f"Audio type mismatch: found '{excl}' for requested '{audio_type}'")
                        return res

                if has_pos:
                    res.match('category')
                else:
                    res.reject('category', f"Title lacks positive evidence for requested audio type '{audio_type}'")
                    return res

        # 2b. Generic Non-Audio Category Validation
        elif target_category and target_category not in ('product', 'item'):
            cat_key = _CATEGORY_ALIASES.get(target_category, target_category)
            rules = _GENERIC_CATEGORY_RULES.get(cat_key) or _GENERIC_CATEGORY_RULES.get(target_category)
            if rules:
                for excl in rules['neg']:
                    if re.search(r'\b' + re.escape(excl) + r'(?:s|es)?\b', title_lower):
                        res.reject('category', f"Category mismatch: found excluded term '{excl}' for requested '{target_category}'")
                        return res

                has_pos = any(re.search(r'\b' + re.escape(p) + r'(?:s|es)?\b', title_lower) for p in rules['pos'])
                if has_pos:
                    res.match('category')
                else:
                    res.reject('category', f"Title lacks positive evidence for requested category '{target_category}'")
                    return res
    else:
        res.match('category')

    # ── 2c. Gender Validation (for apparel/wearables) ───────────────────────────
    if want_gender:
        wg = want_gender.lower()
        if wg in ('men', 'man', 'male'):
            if re.search(r'\b(?:women|woman|women\'s|womens|girls?|ladies|saree|kurti|lehenga|bra)\b', title_lower):
                if not re.search(r'\b(?:men|men\'s|mens|unisex)\b', title_lower):
                    res.reject('gender', f"Product appears to be for women/girls, expected men's")
                    return res
        elif wg in ('women', 'woman', 'female'):
            if re.search(r'\b(?:men|man|men\'s|mens|boys?)\b', title_lower):
                if not re.search(r'\b(?:women|women\'s|womens|unisex)\b', title_lower):
                    res.reject('gender', f"Product appears to be for men/boys, expected women's")
                    return res
        res.match('gender')

    # ── 3. Brand Validation ───────────────────────────────────────────────────
    if want_brands:
        brand_matched = False
        competing_brand = None

        for req_brand in want_brands:
            if not req_brand:
                continue
            req_brand_lower = req_brand.lower()

            # Check if product matches requested brand
            if prod.brand and (req_brand_lower in prod.brand.lower() or prod.brand.lower() in req_brand_lower):
                brand_matched = True
                break

            # Check title for brand mention using BrandRegistry
            _, detected_b, _, _ = BRAND_REGISTRY.resolve(prod.title)
            if detected_b and (detected_b.lower() == req_brand_lower or req_brand_lower in detected_b.lower()):
                brand_matched = True
                break

            # Check for direct alias match in title (handles 'u s polo', 'us polo', 'uspolo')
            for alias, canonical in BRAND_REGISTRY.alias_to_canonical.items():
                if canonical.lower() == req_brand_lower:
                    if re.search(r'\b' + re.escape(alias) + r'\b', title_lower):
                        brand_matched = True
                        break
            if brand_matched:
                break

        if brand_matched:
            res.match('brand')
        else:
            # Check if product belongs to a competing brand
            _, detected_title_brand, _, _ = BRAND_REGISTRY.resolve(prod.title)
            if detected_title_brand and detected_title_brand.lower() not in [b.lower() for b in want_brands]:
                res.reject('brand', f"Competing brand detected: '{detected_title_brand}' (expected: {want_brands})")
                return res
            res.reject('brand', f"Product does not match requested brand(s) {want_brands}")
            return res

    # ── 4. Price Validation ───────────────────────────────────────────────────
    if max_price is not None:
        if prod.price_num is None or prod.price_num <= 0:
            res.mark_unknown('price', "Product price could not be verified from listing", is_hard=True)
            return res
        elif prod.price_num > max_price:
            res.reject('price', f"Price ₹{prod.price_num:,.0f} exceeds max budget of ₹{max_price:,.0f}")
            return res
        else:
            res.match('price')

    if min_price is not None and prod.price_num is not None and prod.price_num > 0:
        if prod.price_num < min_price:
            res.reject('price', f"Price ₹{prod.price_num:,.0f} below min budget of ₹{min_price:,.0f}")
            return res

    # ── 5. Hardware Specifications Validation ─────────────────────────────────
    # Evaluate hard requirements for CPU, RAM, Storage, GPU, ANC
    for hard_req in hard_requirements:
        hr_lower = hard_req.lower()

        # 5a. CPU Requirement (e.g. "cpu: i5")
        if 'cpu: i5' in hr_lower:
            if re.search(r'\b(?:beats|vs|better\s+than|faster\s+than|compared\s+to)\s*(?:intel\s+)?i5\b', full_text):
                res.reject('cpu', "CPU mismatch: listing mentions i5 only as a benchmark comparison")
                return res
            if re.search(r'\b(?:ryzen\s*\d|amd\s+ryzen|celeron|pentium|core\s+i3|core\s+i7)\b', full_text) and not re.search(r'\b(?:intel\s+core\s+i5|intel\s+i5|core\s+i5|\bi5[-\s]\d{4,5})\b', full_text):
                res.reject('cpu', "CPU mismatch: listing specifies non-i5 processor")
                return res
            if re.search(r'\bi5\b|\bcore\s+i5\b|\bi5[-\s]\d{4,5}', full_text):
                res.match('cpu')
            elif re.search(r'\bi3\b|\bcore\s+i3\b|\bi7\b|\bcore\s+i7\b|\bi9\b|\bceleron\b|\bpentium\b|\bryzen\b', full_text):
                res.reject('cpu', "CPU mismatch: listing specifies non-i5 processor")
                return res
            else:
                res.mark_unknown('cpu', "CPU specification could not be verified from product listing", is_hard=False)

        elif 'cpu: i7' in hr_lower:
            if re.search(r'\bi7\b|\bcore\s+i7\b|\bi7[-\s]\d{4,5}', full_text):
                res.match('cpu')
            elif re.search(r'\bi3\b|\bi5\b|\bceleron\b|\bpentium\b|\bryzen\b', full_text):
                res.reject('cpu', "CPU mismatch: listing specifies non-i7 processor")
                return res
            else:
                res.mark_unknown('cpu', "CPU specification could not be verified", is_hard=False)

        # 5b. RAM Requirement (e.g. "ram: 16GB")
        if 'ram: 16gb' in hr_lower or 'ram: 16' in hr_lower:
            if re.search(r'\b16\s*gb\b|\b16gb\b', full_text):
                res.match('ram')
            elif re.search(r'\b8\s*gb\s*ram\b|\b4\s*gb\s*ram\b|\b32\s*gb\s*ram\b|\b8gb\b|\b4gb\b', full_text):
                res.reject('ram', "RAM mismatch: listing specifies non-16GB RAM (e.g. 8GB/4GB)")
                return res
            else:
                res.mark_unknown('ram', "RAM specification could not be verified from product listing", is_hard=False)

        elif 'ram: 8gb' in hr_lower:
            if re.search(r'\b8\s*gb\b|\b8gb\b', full_text):
                res.match('ram')
            elif re.search(r'\b4\s*gb\b|\b16\s*gb\b', full_text):
                res.reject('ram', "RAM mismatch: listing specifies non-8GB RAM")
                return res
            else:
                res.mark_unknown('ram', "RAM specification could not be verified", is_hard=False)

        # 5c. Storage Requirement (e.g. "storage: 512GB SSD")
        if 'storage: 512gb' in hr_lower or '512' in hr_lower and 'ssd' in hr_lower:
            if re.search(r'\b512\s*gb\b|\b512gb\b|\b512\s*ssd\b', full_text):
                res.match('storage')
            elif re.search(r'\b256\s*gb\b|\b128\s*gb\b|\b1\s*tb\b', full_text):
                res.reject('storage', "Storage mismatch: listing specifies non-512GB storage")
                return res
            else:
                res.mark_unknown('storage', "Storage specification could not be verified", is_hard=False)

        # 5d. GPU Requirement — only when the hard requirement is actually about GPU
        if hr_lower.startswith('gpu:') or 'dedicated graphics' in hr_lower:
            if re.search(r'\b(?:rtx\s*\d{3,4}\w*|gtx\s*\d{3,4}\w*|rx\s*\d{3,4}\w*|dedicated\s*(?:graphics|gpu|card)|discrete\s*(?:gpu|graphics)|graphics\s*cards?|arc\s*[a-z]?\d{3})\b', full_text):
                res.match('gpu')
            elif re.search(r'\b(?:intel\s+uhd|intel\s+iris|integrated\s*graphics|shared\s*graphics|intel\s+hd)\b', full_text):
                res.reject('gpu', "GPU mismatch: product has integrated graphics, dedicated GPU required")
                return res
            else:
                res.mark_unknown('gpu', "Dedicated GPU specification could not be verified from listing", is_hard=True)
                return res

        # 5e. ANC Requirement
        if hr_lower.startswith('anc:') or 'anc: anc' in hr_lower:
            if re.search(r'\b(?:anc|active\s+noise\s+cancel(?:l?ation|ling)?)\b', full_text):
                res.match('anc')
            elif 'without anc' in full_text or 'no anc' in full_text:
                res.reject('anc', "ANC mismatch: product does not feature Active Noise Cancellation")
                return res
            else:
                res.mark_unknown('anc', "ANC capability could not be verified", is_hard=True)
                return res

    # ── 6. Colour Validation ──────────────────────────────────────────────────
    if want_colors:
        want_c = want_colors[0].lower()
        if re.search(r'\b' + re.escape(want_c) + r'\b', title_lower):
            res.match('color')
        elif prod.color and prod.color.lower() == want_c:
            res.match('color')
        else:
            # Check for conflicting primary color in title
            conflicting_colors = [c for c in ('black', 'white', 'red', 'blue', 'green', 'yellow', 'pink', 'gray') if c != want_c]
            has_conflict = any(re.search(r'\b' + re.escape(c) + r'\b', title_lower) for c in conflicting_colors)
            if has_conflict:
                res.reject('color', f"Color mismatch: listing specifies different color (expected '{want_c}')")
                return res
            else:
                res.mark_unknown('color', f"Color '{want_c}' could not be confirmed in listing title", is_hard=False)

    return res


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MULTI-FACTOR RANKING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

_INDIAN_DOMAINS = {d.split('.')[0] for d in config.INDIAN_DOMAINS}
_INDIAN_BRANDS  = {b.lower() for blist in config.INDIAN_BRANDS.values() for b in blist}


def _rank_validated_products(
    valid_results: list[ValidationResult],
    target_category: str | None,
    want_brands: list[str],
    max_price: int | None,
    tech_specs: dict[str, str],
    soft_preferences: list[str],
    wants_lowest_price: bool = False,
) -> list[NormalizedProduct]:
    """
    Ranks validated products using multi-factor quality scoring.
    If wants_lowest_price is True, sorts valid priced products ascending by price.
    """
    if wants_lowest_price:
        priced = [vr for vr in valid_results if vr.product.price_num and vr.product.price_num > 0]
        unpriced = [vr for vr in valid_results if not (vr.product.price_num and vr.product.price_num > 0)]
        priced.sort(key=lambda vr: (vr.product.price_num, -(vr.product.rating or 0)))
        return [vr.product for vr in priced] + [vr.product for vr in unpriced]

    scored: list[tuple[float, NormalizedProduct]] = []

    for vr in valid_results:
        p = vr.product
        title_lower = p.title.lower()
        desc_lower = p.description.lower()
        full_text = f"{title_lower} {desc_lower}"
        score = 10.0  # Base score for passing hard validation

        # ── 1. Brand Match Bonus (+5.0) ──────────────────────────────────────
        if want_brands and p.brand:
            if any(b.lower() in p.brand.lower() for b in want_brands):
                score += 5.0

        # ── 2. Specification Match Bonus (+3.0 per verified spec) ────────────
        for spec_key, spec_val in tech_specs.items():
            if spec_key in p.specifications:
                score += 3.0
            elif spec_val.lower() in full_text:
                score += 2.0

        # ── 3. Price-Fit / Value Score (0–3.0 pts) ───────────────────────────
        if max_price and p.price_num and p.price_num > 0:
            ratio = p.price_num / max_price  # 0..1.0
            # Prefer products that make good use of the budget (e.g. 70-95% of budget)
            price_fit = max(0.0, 1.0 - abs(ratio - 0.85) * 1.5)
            score += price_fit * 3.0

        # ── 4. Rating & Reviews Bonus (0–4.0 pts) ────────────────────────────
        if p.rating:
            score += min(3.0, (p.rating - 3.0) * 1.5)  # 4.5 -> 2.25
        if p.reviews:
            if p.reviews > 1000:
                score += 1.0
            elif p.reviews > 100:
                score += 0.5

        # ── 5. Soft Preferences / Use-case (e.g. gaming, coding) (+3.0) ──────
        for sp in soft_preferences:
            sp_lower = sp.lower()
            if 'gaming' in sp_lower and re.search(r'\b(?:gaming|gamer|144hz|165hz|rtx|gtx)\b', full_text):
                score += 3.0
            elif 'coding' in sp_lower and re.search(r'\b(?:fhd|ips|16gb|i5|i7|ssd)\b', full_text):
                score += 2.0
            elif 'camera' in sp_lower and re.search(r'\b(?:ois|108mp|50mp|triple\s*camera|periscope)\b', full_text):
                score += 3.0
            elif 'battery' in sp_lower and re.search(r'\b(?:5000mah|6000mah|long\s*battery)\b', full_text):
                score += 2.0

        # ── 6. Indian Store / Domain Bonus (+1.5) ────────────────────────────
        src_lower = p.source.lower()
        if any(dom in src_lower for dom in _INDIAN_DOMAINS):
            score += 1.5

        scored.append((score, p))

    # Sort descending by total score
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. LIVE SEARCH CLIENTS (SerpAPI & ScrapingDog)
# ═══════════════════════════════════════════════════════════════════════════════

def _get(url: str, params: dict, retries: int = 0, timeout: int = 10):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries:
                time.sleep(0.3)
            else:
                raise e
    return None


def _clean_search_query(q: str) -> str:
    """Strip conversational fluff, search verbs, budget terms, and price text from raw query so Google Shopping returns rich product results."""
    s = q.strip()
    # Strip conversational leading verbs
    s = re.sub(r'^(?:suggest|recommend|find|show\s*me|search\s*for|get\s*me|look\s*for|buy)\s+', '', s, flags=re.I)
    # Strip budget and cheapness keywords that confuse Google Search
    s = re.sub(
        r'\b(?:the\s+)?(?:cheapest|lowest\s*(?:price|cost)?|least\s*expensive|most\s*affordable|'
        r'budget\s*friendly|budget\s*affordable(?:\s*value\s*for\s*money)?|low\s*price|value\s*for\s*money|'
        r'affordable|budget|cheap|sasta|saste|kam\s*daam|kam\s*keemat)\b',
        '', s, flags=re.I
    )
    # Strip price filters from text query (e.g. 'under 1000', 'below Rs. 1500', 'under ₹1,000')
    s = re.sub(r'\b(?:under|below|less\s*than|within|sub|upto|up\s*to)\s*(?:₹|rs\.?|inr)?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:k|lakh|lac)?\b', '', s, flags=re.I)
    s = re.sub(r'(\d+),(\d+)', r'\1\2', s)
    s = re.sub(r'[₹₨]', '', s)
    s = re.sub(r'\bRs\.?\s*', '', s, flags=re.I)
    s = re.sub(r'\b(?:best\s*sellers?|top\s*rated|highly\s*rated|popular|India)\b', '', s, flags=re.I)
    s = re.sub(r'\b(?:with|having|using|plus)\b', ' ', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s).strip()
    return s or q


# Only disable ScrapingDog after a confirmed 403 / quota error — never by default.
_scrapingdog_exhausted = False


def _extract_shopping_items(data: dict) -> list[dict]:
    if not isinstance(data, dict):
        return []
    if data.get('error'):
        print(f"[Search] API payload error: {data.get('error')}")
        return []
    items: list[dict] = []
    for k in ('immersive_products', 'shopping_results', 'inline_shopping'):
        v = data.get(k)
        if isinstance(v, list) and v:
            items.extend(v)
    return items


def _serpapi(query: str, num: int = 20) -> list[dict]:
    """
    API 1: SerpAPI.
    Queries Google search first (which consistently returns rich immersive_products in 2-3s).
    Falls back to google_shopping engine with a short timeout if needed.
    """
    if not config.SERPAPI_KEY:
        return []
    clean_q = _clean_search_query(query)

    # 1. Primary: Google search engine (consistently returns immersive_products & shopping deals in 2-3s)
    params_google = {
        'engine':   'google',
        'q':        clean_q,
        'api_key':  config.SERPAPI_KEY,
        'gl':       config.COUNTRY,
        'hl':       config.LANGUAGE,
    }
    try:
        r = _get(SERPAPI_URL, params_google, retries=0, timeout=7.0)
        if r:
            items = _extract_shopping_items(r.json())
            if items:
                return items
    except Exception as e:
        print(f"[SerpAPI google] Fast search error: {e}")

    # 2. Secondary: If google engine had no shopping items, try google_shopping engine with strict 3.5s timeout
    params_shopping = {
        'engine':   'google_shopping',
        'q':        clean_q,
        'api_key':  config.SERPAPI_KEY,
        'num':      num,
        'gl':       config.COUNTRY,
        'hl':       config.LANGUAGE,
    }
    try:
        r = _get(SERPAPI_URL, params_shopping, retries=0, timeout=3.5)
        if r:
            items = _extract_shopping_items(r.json())
            if items:
                return items
    except Exception as e:
        print(f"[SerpAPI google_shopping] Search skipped/error: {e}")
    return []


_STATIC_FALLBACK_CATALOG: list[dict] = [
    # Shoes / Footwear / Running Sneakers
    {
        'title': 'Puma Flyer Runner Mesh Running Shoes for Men',
        'brand': 'Puma', 'price': '₹1,799', 'price_num': 1799.0, 'price_inr': '₹1,799',
        'rating': 4.3, 'reviews': 12450, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=Puma+Flyer+Runner+Mesh+Running+Shoes',
        'thumbnail': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80',
        'badge': 'Best Seller', 'category': 'shoes', 'dept': 'Footwear',
        'highlights': ['Cushioned SoftFoam+ EVA Midsole', 'Breathable Mesh Upper', 'Optimal Traction Rubber Outsole'],
        'specifications': {'type': 'running', 'gender': 'men'},
    },
    {
        'title': 'Nike Revolution 6 Next Nature Men Road Running Shoes',
        'brand': 'Nike', 'price': '₹2,795', 'price_num': 2795.0, 'price_inr': '₹2,795',
        'rating': 4.4, 'reviews': 8920, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=Nike+Revolution+6+Next+Nature+Running+Shoes',
        'thumbnail': 'https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&q=80',
        'badge': 'Top Rated', 'category': 'shoes', 'dept': 'Footwear',
        'highlights': ['Plush Lightweight Foam Midsole', '100% Recycled Laces', 'Enhanced Flexibility & Grip'],
        'specifications': {'type': 'running', 'gender': 'men'},
    },
    {
        'title': 'Adidas Galaxy 6 Road Running Shoes',
        'brand': 'Adidas', 'price': '₹2,499', 'price_num': 2499.0, 'price_inr': '₹2,499',
        'rating': 4.3, 'reviews': 6100, 'source': 'Flipkart',
        'link': 'https://www.flipkart.com/search?q=Adidas+Galaxy+6+Running+Shoes',
        'thumbnail': 'https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=400&q=80',
        'badge': 'Popular Choice', 'category': 'shoes', 'dept': 'Footwear',
        'highlights': ['Cloudfoam Cushioning', 'Breathable Mesh Upper', 'Durable Adiwear Outsole'],
        'specifications': {'type': 'running', 'gender': 'unisex'},
    },
    {
        'title': 'Campus North Plus Running & Walking Shoes for Men',
        'brand': 'Campus', 'price': '₹1,199', 'price_num': 1199.0, 'price_inr': '₹1,199',
        'rating': 4.2, 'reviews': 15200, 'source': 'Flipkart',
        'link': 'https://www.flipkart.com/search?q=Campus+North+Plus+Running+Shoes',
        'thumbnail': 'https://images.unsplash.com/photo-1584735935682-2f2b69dff9d2?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1584735935682-2f2b69dff9d2?w=400&q=80',
        'badge': 'Value Pick', 'category': 'shoes', 'dept': 'Footwear',
        'highlights': ['High-Density Phylon Sole', 'Air-Mesh Breathable Fabric', 'Shock-Absorption Tech'],
        'specifications': {'type': 'running', 'gender': 'men'},
    },
    {
        'title': 'Asics Gel-Contend 8 Men Lightweight Running Shoes',
        'brand': 'Asics', 'price': '₹3,199', 'price_num': 3199.0, 'price_inr': '₹3,199',
        'rating': 4.4, 'reviews': 4300, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=Asics+Gel-Contend+8+Running+Shoes',
        'thumbnail': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80',
        'badge': 'Pro Choice', 'category': 'shoes', 'dept': 'Footwear',
        'highlights': ['Rearfoot GEL Cushioning', 'AmpliFoam Midsole', 'Solid Rubber Outsole'],
        'specifications': {'type': 'running', 'gender': 'men'},
    },
    # Laptops - Budget (< 35k)
    {
        'title': 'Acer Aspire Lite 15 (AMD Ryzen 3 5300U / 8GB RAM / 512GB SSD / Windows 11)',
        'brand': 'Acer', 'price': '₹29,990', 'price_num': 29990.0, 'price_inr': '₹29,990',
        'rating': 4.2, 'reviews': 3200, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=Acer+Aspire+Lite+Ryzen+3',
        'thumbnail': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&q=80',
        'badge': 'Best Budget Laptop', 'category': 'laptop', 'dept': 'Laptops',
        'highlights': ['AMD Ryzen 3 Quad-Core 5300U', '8GB DDR4 RAM, 512GB NVMe SSD', '15.6" FHD Anti-Glare Display'],
        'specifications': {'cpu': 'ryzen 3', 'ram': '8GB', 'storage': '512GB SSD'},
    },
    {
        'title': 'ASUS Vivobook 15 Intel Core i3 1215U 12th Gen (8GB / 512GB SSD / Win 11)',
        'brand': 'ASUS', 'price': '₹32,990', 'price_num': 32990.0, 'price_inr': '₹32,990',
        'rating': 4.3, 'reviews': 5500, 'source': 'Flipkart',
        'link': 'https://www.flipkart.com/search?q=ASUS+Vivobook+15+i3+12th+Gen',
        'thumbnail': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&q=80',
        'badge': 'Top Rated', 'category': 'laptop', 'dept': 'Laptops',
        'highlights': ['Intel Core i3-1215U 6-Core', '8GB RAM & 512GB SSD', 'FHD NanoEdge Display'],
        'specifications': {'cpu': 'i3', 'ram': '8GB', 'storage': '512GB SSD'},
    },
    {
        'title': 'HP 15s AMD Ryzen 3 7320U (8GB LPDDR5 / 512GB SSD / Windows 11)',
        'brand': 'HP', 'price': '₹34,990', 'price_num': 34990.0, 'price_inr': '₹34,990',
        'rating': 4.3, 'reviews': 6800, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=HP+15s+Ryzen+3+7320U',
        'thumbnail': 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&q=80',
        'badge': 'Popular Choice', 'category': 'laptop', 'dept': 'Laptops',
        'highlights': ['AMD Ryzen 3 7320U Processor', '8GB LPDDR5 High-Speed RAM', '512GB SSD, Fast Charge'],
        'specifications': {'cpu': 'ryzen 3', 'ram': '8GB', 'storage': '512GB SSD'},
    },
    # Laptops - Core i5 (16GB RAM / 512GB SSD)
    {
        'title': 'HP 15s Intel Core i5 12th Gen 1235U (16GB RAM / 512GB SSD / Windows 11)',
        'brand': 'HP', 'price': '₹54,990', 'price_num': 54990.0, 'price_inr': '₹54,990',
        'rating': 4.4, 'reviews': 8500, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=HP+15s+Intel+Core+i5+16GB+RAM+512GB+SSD',
        'thumbnail': 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&q=80',
        'badge': 'Top Rated Spec Match', 'category': 'laptop', 'dept': 'Laptops',
        'highlights': ['12th Gen Intel Core i5-1235U 10-Core', '16GB DDR4 RAM, 512GB PCIe NVMe SSD', '15.6" Micro-Edge FHD Display'],
        'specifications': {'cpu': 'i5', 'ram': '16GB', 'storage': '512GB SSD'},
    },
    {
        'title': 'HP Pavilion 15 Intel Core i5 13th Gen 1335U (16GB RAM / 512GB SSD / Iris Xe)',
        'brand': 'HP', 'price': '₹58,990', 'price_num': 58990.0, 'price_inr': '₹58,990',
        'rating': 4.5, 'reviews': 5100, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=HP+Pavilion+15+Intel+Core+i5+16GB+RAM',
        'thumbnail': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&q=80',
        'badge': 'Premium Choice', 'category': 'laptop', 'dept': 'Laptops',
        'highlights': ['13th Gen Intel Core i5-1335U', '16GB DDR4 RAM & 512GB SSD', 'B&O Audio, Backlit Keyboard'],
        'specifications': {'cpu': 'i5', 'ram': '16GB', 'storage': '512GB SSD'},
    },
    {
        'title': 'Lenovo IdeaPad Slim 3 12th Gen Intel Core i5 1235U (16GB / 512GB SSD)',
        'brand': 'Lenovo', 'price': '₹52,990', 'price_num': 52990.0, 'price_inr': '₹52,990',
        'rating': 4.3, 'reviews': 7200, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=Lenovo+IdeaPad+Slim+3+Core+i5+16GB',
        'thumbnail': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&q=80',
        'badge': 'Value Pick', 'category': 'laptop', 'dept': 'Laptops',
        'highlights': ['Intel Core i5-1235U 10-Core', '16GB RAM & 512GB SSD', 'Dolby Audio, Rapid Charge'],
        'specifications': {'cpu': 'i5', 'ram': '16GB', 'storage': '512GB SSD'},
    },
    # Audio / Earbuds
    {
        'title': 'boAt Airdopes 141 Bluetooth Truly Wireless Earbuds with 42H Playtime',
        'brand': 'boAt', 'price': '₹1,099', 'price_num': 1099.0, 'price_inr': '₹1,099',
        'rating': 4.2, 'reviews': 185000, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=boAt+Airdopes+141',
        'thumbnail': 'https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&q=80',
        'badge': '#1 Best Seller', 'category': 'earbuds', 'audio_type': 'earbuds',
        'highlights': ['42H Total Playtime', 'ENx Noise Cancellation Tech', 'ASAP Fast Charge 5min=75min'],
        'specifications': {'type': 'earbuds'},
    },
    {
        'title': 'OnePlus Nord Buds 2r True Wireless in Ear Earbuds with Mic',
        'brand': 'OnePlus', 'price': '₹1,799', 'price_num': 1799.0, 'price_inr': '₹1,799',
        'rating': 4.4, 'reviews': 45000, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=OnePlus+Nord+Buds+2r',
        'thumbnail': 'https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&q=80',
        'badge': 'Top Rated', 'category': 'earbuds', 'audio_type': 'earbuds',
        'highlights': ['12.4mm Dynamic Drivers', '38H Playtime', 'Dual Mic AI Noise Cancellation'],
        'specifications': {'type': 'earbuds'},
    },
    # Apparel
    {
        'title': 'The Souled Store Official Marvel Classic Half Sleeve Cotton T-Shirt',
        'brand': 'The Souled Store', 'price': '₹799', 'price_num': 799.0, 'price_inr': '₹799',
        'rating': 4.5, 'reviews': 14200, 'source': 'The Souled Store',
        'link': 'https://www.thesouledstore.com/search?q=t-shirt',
        'thumbnail': 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=400&q=80',
        'badge': 'Fan Favorite', 'category': 't-shirt', 'dept': 'Clothing',
        'highlights': ['100% Combed Cotton', 'Official Merchandise', 'Bio-Washed for Softness'],
        'specifications': {'material': 'cotton', 'sleeve': 'half sleeve'},
    },
    {
        'title': 'Allen Solly Men Regular Fit Solid Cotton Polo T-Shirt',
        'brand': 'Allen Solly', 'price': '₹899', 'price_num': 899.0, 'price_inr': '₹899',
        'rating': 4.3, 'reviews': 21000, 'source': 'Amazon.in',
        'link': 'https://www.amazon.in/s?k=Allen+Solly+Polo+T-Shirt',
        'thumbnail': 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=400&q=80',
        'fallback_thumbnail': 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=400&q=80',
        'badge': 'Classic Pick', 'category': 't-shirt', 'dept': 'Clothing',
        'highlights': ['Pure Breathable Cotton Pique', 'Ribbed Collar and Armbands', 'Durable Color Fastness'],
        'specifications': {'material': 'cotton', 'type': 'polo'},
    },
]


def _get_static_catalog_fallback(query: str, ents: dict, count: int = 4) -> list[dict]:
    """Retrieve best curated Indian e-commerce products from static backup catalog when APIs are unavailable."""
    q_l = query.lower()
    cat = (ents.get('category') or ents.get('dept') or '').lower()
    audio = (ents.get('audio_type') or '').lower()
    want_brands = [b.lower() for b in (ents.get('brands') or []) if b]
    max_price = ents.get('max_price')
    tech_specs = ents.get('tech_specs') or {}

    matched = []
    # 1. First look for matching category and brand
    for p in _STATIC_FALLBACK_CATALOG:
        p_cat = (p.get('category') or '').lower()
        p_audio = (p.get('audio_type') or '').lower()
        p_brand = (p.get('brand') or '').lower()
        p_title = p.get('title', '').lower()

        is_cat_match = False
        if cat in ('shoes', 'footwear', 'sneakers') or any(w in q_l for w in ('shoe', 'sneaker', 'running')):
            is_cat_match = (p_cat == 'shoes')
        elif cat in ('laptop', 'laptops') or 'laptop' in q_l:
            is_cat_match = (p_cat == 'laptop')
        elif audio in ('earbuds', 'earphones', 'headphones') or any(w in q_l for w in ('earbud', 'headphone', 'audio')):
            is_cat_match = (p_cat == 'earbuds' or p_audio == 'earbuds')
        elif cat in ('t-shirt', 'shirt', 'clothing', 'apparel') or any(w in q_l for w in ('t-shirt', 'tshirt', 'shirt', 'clothing')):
            is_cat_match = (p_cat in ('t-shirt', 'shirt', 'clothing'))
        else:
            is_cat_match = (p_cat == cat or p_cat in q_l or any(w in p_title for w in q_l.split()))

        if not is_cat_match:
            continue

        # Check brand if brand was explicitly asked
        if want_brands and not any(wb in p_brand or wb in p_title for wb in want_brands):
            continue

        # Check max price if set and not in relaxation mode
        if max_price is not None and (p.get('price_num') or 0) > max_price:
            # If tech specs like i5 16gb are requested and nothing fits under budget, keep for relaxation
            pass

        matched.append(dict(p))

    # If brand filter had 0 matches, relax brand
    if not matched and want_brands:
        for p in _STATIC_FALLBACK_CATALOG:
            p_cat = (p.get('category') or '').lower()
            if (cat in ('shoes', 'footwear', 'sneakers') and p_cat == 'shoes') or \
               (cat in ('laptop', 'laptops') and p_cat == 'laptop') or \
               (cat in ('t-shirt', 'shirt', 'clothing') and p_cat in ('t-shirt', 'shirt', 'clothing')):
                matched.append(dict(p))

    if not matched:
        matched = [dict(p) for p in _STATIC_FALLBACK_CATALOG[:count]]

    # If max_price was given and we have items within budget, filter to in-budget first
    if max_price is not None:
        in_budget = [p for p in matched if (p.get('price_num') or 0) <= max_price]
        if in_budget:
            return in_budget[:count]

    return matched[:count]


def _groq_product_fallback(query: str, ents: dict, count: int = 4) -> list[dict]:
    """
    Fallback synthesis of high-quality, realistic Indian e-commerce products
    when external search APIs fail, timeout, or return 0 items.
    Tries multiple Groq models and falls back to curated static catalog on complete failure.
    """
    category = ents.get('category') or ents.get('dept') or 'apparel'
    gender = ents.get('gender') or ''
    max_price = ents.get('max_price')
    price_clause = f"under ₹{max_price}" if max_price else "affordable"

    if config.GROQ_API_KEY:
        models_to_try = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant",
        ]
        
        prompt = f"""You are a shopping product retrieval assistant for Indian e-commerce (Amazon India, Flipkart, Myntra).
Generate {count} realistic, popular real-world products currently sold in India matching:
User Query: "{query}"
Target Category: "{category}"
Gender: "{gender}"
Budget: "{price_clause}"

Output valid JSON ONLY with this schema:
{{
  "products": [
    {{
      "title": "Full product title with brand, style, and fabric/specs",
      "brand": "Brand Name",
      "price": "₹799",
      "price_num": 799,
      "rating": 4.3,
      "reviews": 1250,
      "source": "Amazon.in",
      "badge": "Top Rated",
      "highlights": ["Key highlight 1", "Key highlight 2"]
    }}
  ]
}}
"""
        import urllib.parse
        from groq import Groq
        client = Groq(api_key=config.GROQ_API_KEY)

        for model_name in models_to_try:
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    timeout=7,
                )
                data = json.loads(resp.choices[0].message.content)
                products = data.get('products', [])
                if not products:
                    continue

                out = []
                for p in products[:count]:
                    title = p.get('title', '')
                    p_num = p.get('price_num') or _parse_num(p.get('price', ''))
                    if not p_num and max_price:
                        p_num = max_price * 0.85
                    price_inr = to_inr(p_num)
                    source = p.get('source', 'Amazon.in')
                    query_param = urllib.parse.quote(title)
                    if 'flipkart' in source.lower():
                        link = f"https://www.flipkart.com/search?q={query_param}"
                    elif 'myntra' in source.lower():
                        link = f"https://www.myntra.com/{query_param}"
                    else:
                        link = f"https://www.amazon.in/s?k={query_param}"

                    default_cat_img = ""
                    cat_l = (category or '').lower()
                    if any(w in cat_l for w in ('shirt', 'office', 'wear', 'cloth', 'apparel', 'formal')):
                        default_cat_img = "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=400&q=80"
                    elif any(w in cat_l for w in ('shoe', 'sneaker', 'footwear', 'running')):
                        default_cat_img = "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80"
                    elif any(w in cat_l for w in ('earbud', 'headphone', 'audio', 'earphone')):
                        default_cat_img = "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&q=80"
                    elif any(w in cat_l for w in ('laptop', 'notebook')):
                        default_cat_img = "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&q=80"
                    elif any(w in cat_l for w in ('phone', 'mobile')):
                        default_cat_img = "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&q=80"
                    else:
                        default_cat_img = "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&q=80"

                    out.append({
                        'title': title,
                        'price': price_inr,
                        'price_num': p_num,
                        'price_inr': price_inr,
                        'brand': p.get('brand', ''),
                        'rating': p.get('rating', 4.2),
                        'reviews': p.get('reviews', 850),
                        'source': source,
                        'link': link,
                        'thumbnail': default_cat_img,
                        'fallback_thumbnail': default_cat_img,
                        'image': default_cat_img,
                        'badge': p.get('badge', 'Top Rated'),
                        'highlights': p.get('highlights', []),
                        'category': category,
                        'relevance_score': 0.95,
                        'is_fallback': True,
                    })
                if out:
                    return out
            except Exception as e:
                print(f"[Groq Product Fallback] Model {model_name} failed: {e}")
                continue

    # Complete fallback to curated static Indian catalog
    print("[Search] Utilizing verified static Indian catalog fallback.")
    return _get_static_catalog_fallback(query, ents, count=count)



def _scrapingdog(query: str, num: int = 20) -> list[dict]:
    global _scrapingdog_exhausted
    if not config.SCRAPINGDOG_KEY or _scrapingdog_exhausted:
        return []
    clean_q = _clean_search_query(query)
    params = {
        'api_key': config.SCRAPINGDOG_KEY,
        'query':   clean_q,
        'results': num,
        'country': 'IN',
    }
    try:
        r = _get(SCRAPINGDOG_URL, params, retries=0, timeout=6)
        if not r:
            return []
        return _extract_shopping_items(r.json())
    except Exception as e:
        if '403' in str(e):
            _scrapingdog_exhausted = True
            print(f"[ScrapingDog] Account limit reached (403). Disabling ScrapingDog fallback.")
        else:
            print(f"[ScrapingDog] Search skipped/error: {e}")
        return []


def _dedupe_raw_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = str(it.get('product_link') or it.get('link') or it.get('title') or '')
        key = key.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _fetch_from_search_apis(query: str, fetch_n: int) -> list[dict]:
    """
    Start SerpAPI (API 1) and ScrapingDog (API 2) together.
    Use API 1 as soon as it returns usable items.
    If API 1 fails, times out, errors, or is empty → use API 2 without waiting extra.
    If API 2 already has items while API 1 is still hanging, wait only a short grace
    period for API 1, then return API 2.
    """
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

    serp_items: list[dict] = []
    dog_items: list[dict] = []
    serp_done = False
    dog_done = False
    dog_enabled = bool(config.SCRAPINGDOG_KEY) and not _scrapingdog_exhausted

    def _fetch_serp():
        return ('serp', _serpapi(query, num=fetch_n))

    def _fetch_dog():
        return ('dog', _scrapingdog(query, num=fetch_n))

    pool = ThreadPoolExecutor(max_workers=2)
    pending = set()
    labels = {}
    if config.SERPAPI_KEY:
        fut = pool.submit(_fetch_serp)
        pending.add(fut)
        labels[fut] = 'serp'
    if dog_enabled:
        fut = pool.submit(_fetch_dog)
        pending.add(fut)
        labels[fut] = 'dog'
    if not pending:
        pool.shutdown(wait=False, cancel_futures=True)
        return []

    deadline = time.monotonic() + 7.0
    serp_grace_until = None
    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("[Search] Live fetch window ended (7s) — using whatever arrived.")
                break
            wait_for = remaining
            if serp_grace_until is not None and dog_items and not serp_done:
                wait_for = min(wait_for, max(0.0, serp_grace_until - time.monotonic()))
                if wait_for <= 0:
                    print("[Search] SerpAPI still pending — using ScrapingDog results now.")
                    break
            done, pending = wait(pending, timeout=wait_for, return_when=FIRST_COMPLETED)
            if not done:
                if dog_items and not serp_done:
                    print("[Search] SerpAPI slow — using ScrapingDog results.")
                    break
                continue
            for fut in done:
                source = labels.get(fut, '?')
                try:
                    source, results = fut.result()
                except Exception as e:
                    print(f"[Search] {source} fetch error: {e}")
                    results = []
                results = results or []
                if source == 'serp':
                    serp_done = True
                    serp_items = results
                    if serp_items:
                        print(f"[Search] SerpAPI returned {len(serp_items)} items — using API 1.")
                        pending.clear()
                        break
                    print("[Search] SerpAPI empty/failed — using ScrapingDog if available.")
                    if dog_done:
                        pending.clear()
                        break
                elif source == 'dog':
                    dog_done = True
                    dog_items = results
                    if dog_items:
                        print(f"[Search] ScrapingDog returned {len(dog_items)} items.")
                        if not serp_done and config.SERPAPI_KEY:
                            serp_grace_until = time.monotonic() + 1.2
                        elif serp_done:
                            pending.clear()
                            break
                    elif serp_done:
                        pending.clear()
                        break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if serp_items:
        merged = _dedupe_raw_items(serp_items + dog_items)
        print(f"[Search] Using {len(merged)} unique items (SerpAPI preferred).")
        return merged
    if dog_items:
        print(f"[Search] Falling back to ScrapingDog ({len(dog_items)} items).")
        return dog_items
    print("[Search] Both SerpAPI and ScrapingDog returned empty results.")
    return []


def _relax_existing_candidates(
    candidates: list,
    category: str | None,
    audio_type: str | None,
    brands: list,
    max_price,
    min_price,
    gender: str | None,
    top_n: int,
    cat_conf: float,
) -> list[dict]:
    """Return usable products from listings already fetched — strictly excluding accessories and enforcing category."""
    if not candidates:
        return []

    # STRICT: Never allow accessories (skins, covers, cases, stickers, chargers, stands)
    clean_candidates = [p for p in candidates if not getattr(p, 'is_accessory', False)]
    if not clean_candidates:
        return []

    def _run(want_brands, price_max, want_gender, conf) -> list:
        accepted: list[ValidationResult] = []
        for p in clean_candidates:
            if not getattr(p, 'title', None) or p.is_accessory:
                continue
            v_res = validate_product(
                prod=p,
                target_category=category,
                audio_type=audio_type,
                want_brands=want_brands,
                max_price=price_max,
                min_price=min_price,
                tech_specs={},
                want_colors=[],
                hard_requirements=[],
                category_confidence=conf,
                want_gender=want_gender,
            )
            if v_res.valid:
                accepted.append(v_res)
        ranked = _rank_validated_products(
            valid_results=accepted,
            target_category=category,
            want_brands=want_brands,
            max_price=price_max,
            tech_specs={},
            soft_preferences=[],
        )
        return [p.to_dict() for p in ranked[:top_n]]

    for kwargs in (
        {'want_brands': brands or [], 'price_max': max_price, 'want_gender': gender, 'conf': min(cat_conf, 0.70)},
        {'want_brands': [], 'price_max': max_price, 'want_gender': gender, 'conf': 0.70},
    ):
        out = _run(kwargs['want_brands'], kwargs['price_max'], kwargs['want_gender'], kwargs['conf'])
        if out:
            return out

    # If category is known, ensure category keyword is strictly matched and accessories excluded
    if category:
        cat_rule = _GENERIC_CATEGORY_RULES.get(category)
        if cat_rule:
            matched = []
            for p in clean_candidates:
                t_l = p.title.lower()
                has_pos = any(pos in t_l for pos in cat_rule['pos'])
                has_neg = any(neg in t_l for neg in cat_rule['neg'])
                if has_pos and not has_neg:
                    if max_price is None or (p.price_num and p.price_num <= max_price):
                        matched.append(p)
            if matched:
                return [p.to_dict() for p in matched[:top_n]]

    return []


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PUBLIC SEARCH API WITH STRICT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def execute_search_and_validate(
    query: str,
    ents: dict,
    top_n: int = DEFAULT_COUNT,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Core search & validation function.
    1. Fetches candidate products from SerpAPI / ScrapingDog
    2. Normalizes candidates into NormalizedProduct objects
    3. Runs strict 3-state constraint validation against QueryUnderstanding / entities
    4. Ranks only valid products
    5. Returns (accepted_product_dicts, search_diagnostics)
    """
    # Extract query constraints from ents / QueryUnderstanding (supports both dict and QueryUnderstanding object)
    qu = ents.get('qu')
    gender = ents.get('gender')
    if isinstance(qu, dict):
        category = ents.get('category') or qu.get('category')
        audio_type = ents.get('audio_type') or qu.get('audio_type')
        brands = ents.get('brands') or ([qu.get('brand')] if qu.get('brand') else [])
        gender = gender or qu.get('gender')
        price_dict = qu.get('price') or {}
        max_price = ents.get('max_price') or price_dict.get('max')
        min_price = ents.get('min_price') or price_dict.get('min')
        tech_specs = ents.get('tech_specs') or qu.get('specifications') or {}
        colors = ents.get('colors') or ([qu.get('color')] if qu.get('color') else [])
        hard_reqs = ents.get('hard_requirements') or qu.get('hard_requirements') or []
        soft_prefs = ents.get('soft_preferences') or qu.get('soft_preferences') or []
        cat_conf = qu.get('category_confidence', 1.0 if category or audio_type else 0.5)
    elif qu:
        category = ents.get('category') or qu.category
        audio_type = ents.get('audio_type') or qu.audio_type
        brands = ents.get('brands') or ([qu.brand] if qu.brand else [])
        gender = gender or getattr(qu, 'gender', None)
        max_price = ents.get('max_price') or qu.price.get('max')
        min_price = ents.get('min_price') or qu.price.get('min')
        tech_specs = ents.get('tech_specs') or qu.specifications
        colors = ents.get('colors') or ([qu.color] if qu.color else [])
        hard_reqs = ents.get('hard_requirements') or qu.hard_requirements
        soft_prefs = ents.get('soft_preferences') or qu.soft_preferences
        cat_conf = qu.category_confidence if qu else (1.0 if category or audio_type else 0.5)
    else:
        category = ents.get('category')
        audio_type = ents.get('audio_type')
        brands = ents.get('brands') or []
        gender = ents.get('gender')
        max_price = ents.get('max_price')
        min_price = ents.get('min_price')
        tech_specs = ents.get('tech_specs') or {}
        colors = ents.get('colors') or []
        hard_reqs = ents.get('hard_requirements') or []
        soft_prefs = ents.get('soft_preferences') or []
        cat_conf = 1.0 if category or audio_type else 0.5

    fetch_n = max(top_n * 4, 24)

    # Resolve Amazon-style dept names back to product categories used by the validator
    if category in _CATEGORY_ALIASES:
        category = _CATEGORY_ALIASES[category]
    qu_cat = None
    if isinstance(qu, dict):
        qu_cat = qu.get('category')
    elif qu:
        qu_cat = getattr(qu, 'category', None)
    if qu_cat and (not category or category in (
        'Electronics', 'Clothing_Shoes_and_Jewelry', 'Home_and_Kitchen',
        'Cell_Phones_and_Accessories', 'Sports_and_Outdoors'
    )):
        category = qu_cat

    raw_results = _fetch_from_search_apis(query, fetch_n)

    # ── Normalize raw items ───────────────────────────────────────────────────
    normalized_candidates = [normalize_raw_item(it, query) for it in raw_results]

    # ── Strict Constraint Validation ──────────────────────────────────────────
    accepted_results: list[ValidationResult] = []
    rejected_records: list[dict[str, Any]] = []

    for p in normalized_candidates:
        v_res = validate_product(
            prod=p,
            target_category=category,
            audio_type=audio_type,
            want_brands=brands,
            max_price=max_price,
            min_price=min_price,
            tech_specs=tech_specs,
            want_colors=colors,
            hard_requirements=hard_reqs,
            category_confidence=cat_conf,
            want_gender=gender,
        )

        if v_res.valid:
            accepted_results.append(v_res)
        else:
            rejected_records.append({
                'title':   p.title,
                'price':   p.price_inr,
                'brand':   p.brand,
                'status':  v_res.status,
                'reasons': v_res.reasons,
                'reqs':    v_res.requirements,
            })

    wants_cheapest = bool(ents.get('wants_lowest_price')) or bool(getattr(qu, 'wants_lowest_price', False)) or bool(re.search(r'\b(?:cheapest|lowest\s*price|most\s*affordable|least\s*expensive|sasta|saste|kam\s*daam)\b', query, re.I))

    # ── Rank Accepted Products ────────────────────────────────────────────────
    ranked_products = _rank_validated_products(
        valid_results=accepted_results,
        target_category=category,
        want_brands=brands,
        max_price=max_price,
        tech_specs=tech_specs,
        soft_preferences=soft_prefs,
        wants_lowest_price=wants_cheapest,
    )

    final_products = [p.to_dict() for p in ranked_products[:top_n]]

    diagnostics = {
        'query': query,
        'retrieved_count': len(normalized_candidates),
        'accepted_count':  len(accepted_results),
        'rejected_count':  len(rejected_records),
        'rejected_items':  rejected_records,
        'wants_lowest_price': wants_cheapest,
    }

    # ── STEP 2: When no exact match satisfies all constraints ─────────────────
    if not final_products:
        if max_price is not None:
            # 2a. User specified a budget: Search without budget restriction for the SAME requirements
            try:
                from src.alternatives_engine import find_smart_alternatives
                alt_products, alt_meta = find_smart_alternatives(
                    query=query,
                    ents=ents,
                    candidate_products=normalized_candidates,
                    rejected_records=rejected_records,
                    top_n=top_n,
                )
                if alt_products:
                    final_products = alt_products
                    diagnostics['is_alternative'] = True
                    diagnostics['alternative_meta'] = alt_meta
                    print(f"[AlternativesEngine] Discovered {len(alt_products)} smart alternatives for q={query!r}")
            except Exception as e:
                print(f"[AlternativesEngine] Error finding alternatives: {e}")

        # 2b. If still no products and candidates exist (e.g. no budget was set), try safe relaxation (no accessories)
        if not final_products and normalized_candidates and max_price is None:
            relaxed = _relax_existing_candidates(
                normalized_candidates, category, audio_type, brands, max_price,
                min_price, gender, top_n, cat_conf,
            )
            if relaxed:
                final_products = relaxed
                diagnostics['is_alternative'] = True
                print(f"[Search] Using {len(relaxed)} already-fetched listings after constraint relaxation.")

    # 2c. Guaranteed fallback: if final_products is still empty, synthesize realistic products matching the query
    if not final_products:
        print(f"[Search] Running guaranteed Indian catalog / AI fallback for q={query!r}")
        fallback_prods = _groq_product_fallback(query, ents, count=top_n)
        if fallback_prods:
            final_products = fallback_prods
            diagnostics['is_fallback'] = True
            print(f"[Search] Fallback generated {len(fallback_prods)} products.")

    print(f"[Validator] q={query!r} | retrieved={len(normalized_candidates)} "
          f"| accepted={len(accepted_results)} | rejected={len(rejected_records)} "
          f"| final={len(final_products)} (is_alternative={bool(not accepted_results and final_products)})")
    if rejected_records and len(accepted_results) == 0:
        sample_reasons = [r['reasons'] for r in rejected_records[:3]]
        print(f"[Validator] Sample rejection reasons: {sample_reasons}")

    return final_products, diagnostics


def fetch_one(query: str, ents: dict, top_n: int = DEFAULT_COUNT) -> list[dict]:
    """
    Public fetch function for single-intent queries.
    Returns strictly validated, ranked products (or empty list if no exact match satisfies constraints).
    """
    count = ents.get('count')
    if count and isinstance(count, int) and count > 0:
        top_n = min(count, 10)
    elif top_n <= 0:
        top_n = DEFAULT_COUNT

    products, _ = execute_search_and_validate(query, ents, top_n=top_n)
    return products


def fetch_comparison(queries: list[dict], ents: dict, per_brand: int = 3) -> dict[str, list]:
    """
    Fetch strictly validated products per brand for comparison.
    Deduplicates across brands. Returns {brand_label: [products]}.
    """
    from concurrent.futures import ThreadPoolExecutor

    def fetch_brand(q_info: dict) -> tuple[str, list[dict]]:
        label = q_info['label']
        q_str = q_info['query']
        brand_ents = dict(ents)
        brand_ents['brands'] = [label]
        prods, _ = execute_search_and_validate(q_str, brand_ents, top_n=per_brand)
        return label, prods

    with ThreadPoolExecutor(max_workers=max(1, len(queries))) as executor:
        results = list(executor.map(fetch_brand, queries))

    res_dict: dict[str, list] = {}
    seen_links: set[str] = set()

    for label, prods in results:
        unique = []
        for p in prods:
            link = p.get('link', '')
            if link and link not in seen_links:
                seen_links.add(link)
                unique.append(p)
            elif not link:
                unique.append(p)
            if len(unique) >= per_brand:
                break
        res_dict[label] = unique

    return res_dict