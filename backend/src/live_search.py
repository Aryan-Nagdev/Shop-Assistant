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

    if '$' in s:
        num = _parse_num(s)
        return f"₹{num * config.USD_TO_INR:,.0f}" if num else s

    num = _parse_num(s)
    if num is not None:
        if num < 10:
            return f"₹{num * config.USD_TO_INR:,.0f}"
        return f"₹{num:,.0f}"

    return s


def _numeric_inr(price_raw: Any) -> float:
    """Extract numeric INR price value, handling USD conversion and noise."""
    s = str(price_raw or '')
    num = _parse_num(s)
    if num is None:
        return 0.0
    if '$' in s:
        return num * config.USD_TO_INR
    if num < 10:
        return num * config.USD_TO_INR
    return num


def _extract_selling_price(it: dict) -> tuple[float | None, str]:
    """
    Carefully extract actual current selling price from search result item metadata.
    Avoids MRP, crossed-out original prices, EMI amounts, or discount percentages.
    """
    # Check extracted_price / price fields
    price_val = it.get('extracted_price') or it.get('price')
    if price_val is not None:
        num = _numeric_inr(price_val)
        if num > 0:
            return num, to_inr(num)

    # Check raw price string in title / snippet if missing
    text = f"{it.get('title', '')} {it.get('snippet', '')}"
    m = re.search(r'(?:₹|Rs\.?|INR)\s*(\d[\d,]*)', text, re.I)
    if m:
        num = float(m.group(1).replace(',', ''))
        if num > 0:
            return num, to_inr(num)

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
        rating: float | None = None,
        reviews: int | None = None,
        is_accessory: bool = False,
        raw: dict | None = None,
    ):
        self.title          = title
        self.brand          = brand
        self.category       = category
        self.price_num      = price_num
        self.price_inr      = price_inr
        self.currency       = currency
        self.color          = color
        self.specifications = specifications or {}
        self.description    = description
        self.source         = source
        self.link           = link
        self.thumbnail      = thumbnail
        self.rating         = rating
        self.reviews        = reviews
        self.is_accessory   = is_accessory
        self.raw            = raw or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert normalized product into standard dictionary for responses and UI."""
        return {
            'title':          self.title,
            'brand':          self.brand,
            'category':       self.category,
            'price_inr':      self.price_inr,
            'price_num':      self.price_num or 0.0,
            'rating':         self.rating,
            'reviews':        self.reviews,
            'source':         self.source,
            'link':           self.link,
            'thumbnail':      self.thumbnail,
            'color':          self.color,
            'specifications': self.specifications,
        }

    def __repr__(self) -> str:
        return f"<NormalizedProduct title={self.title[:30]!r} brand={self.brand!r} price={self.price_inr} cat={self.category!r}>"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ACCESSORY & EXCLUSION FILTER
# ═══════════════════════════════════════════════════════════════════════════════

_ACCESSORY_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b(?:case|cover|skin|sleeve|pouch|protector|tempered\s*glass|guard)\b', re.I),
    re.compile(r'\b(?:cable|charger|adapter|cord|power\s*adapter|charging\s*dock|charging\s*case\s*only)\b', re.I),
    re.compile(r'\b(?:stand|holder|mount|bracket|tripod)\b', re.I),
    re.compile(r'\b(?:replacement\s*tips|ear\s*tips|ear\s*pads|ear\s*cushions|cushion\s*pads|eartips|silicone\s*tips)\b', re.I),
    re.compile(r'\b(?:watch\s*strap|band\s*strap|replacement\s*band|wrist\s*strap)\b', re.I),
    re.compile(r'\b(?:shoe\s*polish|shoe\s*rack|shoe\s*tree|shoe\s*bag|shoe\s*laces|insole|heel\s*pads)\b', re.I),
    re.compile(r'\b(?:cleaning\s*kit|dust\s*plug|anti\s*dust|keyboard\s*skin|keyboard\s*cover|screen\s*guard)\b', re.I),
    re.compile(r'\b(?:pen\s*drive|pendrive|flash\s*drive|memory\s*card|microsd|sd\s*card|lga\s*\d+|cpu\s*only|processor\s*only|desktop\s*processor)\b', re.I),
    re.compile(r'\b(?:dummy\s*phone|toy\s*phone|toy\s*laptop)\b', re.I),
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


def _fallback_link(title: str) -> str:
    return f"https://www.flipkart.com/search?q={requests.utils.quote(title or 'product')}"


def normalize_raw_item(it: dict, fallback_query: str) -> NormalizedProduct:
    """
    Converts a raw search result dictionary (from SerpAPI/ScrapingDog) into NormalizedProduct.
    Extracts brand, category, specs, colors, and price.
    """
    title = str(it.get('title') or '').strip()
    snippet = str(it.get('snippet') or it.get('description') or '').strip()
    combined_text = f"{title} {snippet}"

    # Price
    price_num, price_inr = _extract_selling_price(it)

    # Link
    link = (_valid_link(it.get('link'))
            or _valid_link(it.get('product_link'))
            or _fallback_link(title or fallback_query))

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

    return NormalizedProduct(
        title=title,
        brand=detected_brand,
        price_num=price_num,
        price_inr=price_inr,
        currency="INR",
        color=detected_color,
        specifications=specs,
        description=snippet,
        source=str(it.get('source') or '').strip(),
        link=link,
        thumbnail=str(it.get('thumbnail') or '').strip(),
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
                'toy laptop', 'laptop bag', 'mouse pad', 'keyboard skin'],
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
        'pos': ['t-shirt', 'tshirt', 't shirt', 'tee', 'polo t-shirt'],
        'neg': ['jeans', 'shoes', 'trouser', 'jacket', 'track pant'],
    },
    'shirt': {
        'pos': ['formal shirt', 'casual shirt', 'cotton shirt', 'linen shirt', 'shirt'],
        'neg': ['t-shirt', 'tshirt', 'jeans', 'shoes'],
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
            rules = _GENERIC_CATEGORY_RULES.get(target_category)
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
                res.mark_unknown('cpu', "CPU specification could not be verified from product listing", is_hard=True)
                return res

        elif 'cpu: i7' in hr_lower:
            if re.search(r'\bi7\b|\bcore\s+i7\b|\bi7[-\s]\d{4,5}', full_text):
                res.match('cpu')
            elif re.search(r'\bi3\b|\bi5\b|\bceleron\b|\bpentium\b|\bryzen\b', full_text):
                res.reject('cpu', "CPU mismatch: listing specifies non-i7 processor")
                return res
            else:
                res.mark_unknown('cpu', "CPU specification could not be verified", is_hard=True)
                return res

        # 5b. RAM Requirement (e.g. "ram: 16GB")
        if 'ram: 16gb' in hr_lower or 'ram: 16' in hr_lower:
            if re.search(r'\b16\s*gb\b|\b16gb\b', full_text):
                res.match('ram')
            elif re.search(r'\b8\s*gb\s*ram\b|\b4\s*gb\s*ram\b|\b32\s*gb\s*ram\b|\b8gb\b|\b4gb\b', full_text):
                res.reject('ram', "RAM mismatch: listing specifies non-16GB RAM (e.g. 8GB/4GB)")
                return res
            else:
                res.mark_unknown('ram', "RAM specification could not be verified from product listing", is_hard=True)
                return res

        elif 'ram: 8gb' in hr_lower:
            if re.search(r'\b8\s*gb\b|\b8gb\b', full_text):
                res.match('ram')
            elif re.search(r'\b4\s*gb\b|\b16\s*gb\b', full_text):
                res.reject('ram', "RAM mismatch: listing specifies non-8GB RAM")
                return res
            else:
                res.mark_unknown('ram', "RAM specification could not be verified", is_hard=True)
                return res

        # 5c. Storage Requirement (e.g. "storage: 512GB SSD")
        if 'storage: 512gb' in hr_lower or '512' in hr_lower and 'ssd' in hr_lower:
            if re.search(r'\b512\s*gb\b|\b512gb\b|\b512\s*ssd\b', full_text):
                res.match('storage')
            elif re.search(r'\b256\s*gb\b|\b128\s*gb\b|\b1\s*tb\b', full_text):
                res.reject('storage', "Storage mismatch: listing specifies non-512GB storage")
                return res
            else:
                res.mark_unknown('storage', "Storage specification could not be verified", is_hard=True)
                return res

        # 5d. GPU Requirement (e.g. "gpu: dedicated", "gpu: rtx", "gpu: dedicated graphics")
        if 'gpu:' in hr_lower or 'dedicated graphics' in hr_lower or 'rtx' in hr_lower or 'graphics card' in hr_lower or 'gpu' in hr_lower:
            if re.search(r'\b(?:rtx\s*\d{3,4}\w*|gtx\s*\d{3,4}\w*|rx\s*\d{3,4}\w*|dedicated\s*(?:graphics|gpu|card)|discrete\s*(?:gpu|graphics)|graphics\s*cards?|arc\s*[a-z]?\d{3})\b', full_text):
                res.match('gpu')
            elif re.search(r'\b(?:intel\s+uhd|intel\s+iris|integrated\s*graphics|shared\s*graphics|intel\s+hd)\b', full_text):
                res.reject('gpu', "GPU mismatch: product has integrated graphics, dedicated GPU required")
                return res
            else:
                res.mark_unknown('gpu', "Dedicated GPU specification could not be verified from listing", is_hard=True)
                return res

        # 5e. ANC Requirement
        if 'anc: anc' in hr_lower or 'anc' in hr_lower:
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
) -> list[NormalizedProduct]:
    """
    Ranks validated products using multi-factor quality scoring.
    Order of priority:
      1. Hard constraint satisfaction (all products have passed validation)
      2. Specification match depth & precision
      3. Brand exactness
      4. Price value / budget efficiency
      5. Customer rating & review depth
      6. Soft preferences / use-case alignment
    """
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

def _get(url: str, params: dict, retries: int = 1, timeout: int = 8):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries:
                time.sleep(0.5)
            else:
                raise e
    return None


def _serpapi(query: str, num: int = 20) -> list[dict]:
    if not config.SERPAPI_KEY:
        return []
    params = {
        'engine':   'google_shopping',
        'q':        query,
        'api_key':  config.SERPAPI_KEY,
        'num':      num,
        'gl':       config.COUNTRY,
        'hl':       config.LANGUAGE,
    }
    try:
        r = _get(SERPAPI_URL, params, retries=1, timeout=8)
        return r.json().get('shopping_results', []) if r else []
    except Exception as e:
        print(f"[SerpAPI] Search skipped/error: {e}")
        return []


def _scrapingdog(query: str, num: int = 20) -> list[dict]:
    if not config.SCRAPINGDOG_KEY:
        return []
    params = {
        'api_key': config.SCRAPINGDOG_KEY,
        'query':   query,
        'results': num,
        'country': 'IN',
    }
    try:
        r = _get(SCRAPINGDOG_URL, params, retries=1, timeout=8)
        return r.json().get('shopping_results', []) if r else []
    except Exception as e:
        print(f"[ScrapingDog] Search skipped/error: {e}")
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
    if isinstance(qu, dict):
        category = ents.get('category') or qu.get('category')
        audio_type = ents.get('audio_type') or qu.get('audio_type')
        brands = ents.get('brands') or ([qu.get('brand')] if qu.get('brand') else [])
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
        max_price = ents.get('max_price')
        min_price = ents.get('min_price')
        tech_specs = ents.get('tech_specs') or {}
        colors = ents.get('colors') or []
        hard_reqs = ents.get('hard_requirements') or []
        soft_prefs = ents.get('soft_preferences') or []
        cat_conf = 1.0 if category or audio_type else 0.5

    fetch_n = max(top_n * 4, 24)

    # ── Fetch raw results ─────────────────────────────────────────────────────
    raw_results = _serpapi(query, num=fetch_n)
    if not raw_results:
        raw_results = _scrapingdog(query, num=fetch_n)

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

    # ── Rank Accepted Products ────────────────────────────────────────────────
    ranked_products = _rank_validated_products(
        valid_results=accepted_results,
        target_category=category,
        want_brands=brands,
        max_price=max_price,
        tech_specs=tech_specs,
        soft_preferences=soft_prefs,
    )

    final_products = [p.to_dict() for p in ranked_products[:top_n]]

    # ── If No Exact Matches Found: Discover Smart Alternatives (Phase 3) ─────
    if not final_products:
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

    diagnostics = {
        'query': query,
        'retrieved_count': len(normalized_candidates),
        'accepted_count':  len(accepted_results),
        'rejected_count':  len(rejected_records),
        'rejected_items':  rejected_records,
    }

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