"""
query_understanding.py  –  Robust AI Query Understanding Layer (Phase 1)
────────────────────────────────────────────────────────────────────────
Architectural Hierarchy:
  Explicit user information
          ↓
  Deterministic normalization (Safe RapidFuzz matching, brand resolution, color normalization, spec/price parsing)
          ↓
  NLU Engine (nlu_engine.py)
          ↓
  LLM interpretation (llm_reason.py)

Key Principles:
  1. Explicit user intent ALWAYS wins (LLM cannot override explicit category/audio_type/brand/specs).
  2. Confidence scoring based on actual match quality.
  3. Strict Hard vs Soft requirements classification.
  4. Extensible brand-resolution system with normalized token keys + RapidFuzz.
  5. Token-boundary safe fuzzy matching (no 'bluetooth' -> 'blue' corruption).
  6. Clarification gate only triggers when shopping intent cannot be identified.
  7. Full preservation of original_query and normalized_query.
  8. Debug explanation mode available via .explain().
"""
from __future__ import annotations
import re
import sys
import os
from typing import Any

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass

# Optional RapidFuzz import (graceful fallback if not present)
try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False
    print("[QueryUnderstanding] rapidfuzz not installed — fuzzy matching will use heuristic fallback. "
          "Run: pip install rapidfuzz")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. EXTENSIBLE BRAND RESOLUTION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

# Core canonical brand definitions with known aliases & abbreviations.
# To add a brand: simply add (Canonical Name, [list of aliases/variations]).
_RAW_BRAND_DEFINITIONS: list[tuple[str, list[str]]] = [
    # Fashion & Apparel
    ("U.S. Polo Assn.", [
        "u s polo assn", "us polo assn", "u.s polo assn", "u.s. polo assn",
        "u s polo ass", "us polo ass", "u s polo", "us polo", "u.s polo",
        "u.s. polo", "uspolo", "uspoloassn", "uspoloass", "polo assn", "us polo association"
    ]),
    ("The Souled Store", [
        "the souled store", "souled store", "souledstore", "the soul store",
        "soul store", "soulstore", "souled"
    ]),
    ("Red Tape", ["red tape", "redtape", "red-tape"]),
    ("Levi's", ["levis", "levi's", "levi", "levis jeans", "levi strauss"]),
    ("Roadster", ["roadster"]),
    ("HRX", ["hrx", "hrx by hrithik roshan"]),
    ("H&M", ["h&m", "h and m", "hm", "h & m"]),
    ("Zara", ["zara"]),
    ("Nike", ["nike", "nke"]),
    ("Adidas", ["adidas", "addidas", "adi das"]),
    ("Puma", ["puma"]),
    ("Reebok", ["reebok", "rebok"]),
    ("Skechers", ["skechers", "sketchers", "skecher"]),
    ("Bata", ["bata"]),
    ("Liberty", ["liberty"]),
    ("Crocs", ["crocs", "croc"]),
    ("Woodland", ["woodland", "woodlands"]),
    ("Allen Solly", ["allen solly", "allensolly"]),
    ("Peter England", ["peter england", "peterengland"]),
    ("Louis Philippe", ["louis philippe", "louisphilippe", "lp"]),
    ("Van Heusen", ["van heusen", "vanheusen"]),
    ("Arrow", ["arrow"]),
    ("Raymond", ["raymond", "raymonds"]),
    ("Monte Carlo", ["monte carlo", "montecarlo"]),
    ("Fabindia", ["fabindia", "fab india"]),
    ("Manyavar", ["manyavar"]),
    ("Biba", ["biba"]),
    ("W", ["w for woman", "w"]),
    ("Libas", ["libas"]),
    ("Jaipur Kurti", ["jaipur kurti"]),
    ("Global Desi", ["global desi"]),
    ("Flying Machine", ["flying machine", "flyingmachine"]),
    ("Pepe Jeans", ["pepe jeans", "pepe"]),
    ("Wrangler", ["wrangler"]),
    ("Lee", ["lee"]),
    ("Spykar", ["spykar"]),
    ("Campus", ["campus shoes", "campus"]),
    ("Sparx", ["sparx"]),

    # Electronics / Tech / Audio
    ("Apple", ["apple", "aple", "appel"]),
    ("Samsung", ["samsung", "samsng", "samung", "samssung"]),
    ("Sony", ["sony"]),
    ("boAt", ["boat", "bo at", "bo-at"]),
    ("Noise", ["noise", "gonoise"]),
    ("Fire-Boltt", ["fire-boltt", "fire boltt", "fireboltt", "boltt"]),
    ("OnePlus", ["oneplus", "one plus", "1plus", "1+"]),
    ("Realme", ["realme", "real me", "relme"]),
    ("Xiaomi", ["xiaomi", "xaomi", "mi", "redmi", "poco"]),
    ("Vivo", ["vivo"]),
    ("Oppo", ["oppo"]),
    ("iQOO", ["iqoo", "i qoo"]),
    ("Motorola", ["motorola", "moto"]),
    ("Nothing", ["nothing phone", "nothing"]),
    ("Google", ["google pixel", "pixel", "google"]),
    ("JBL", ["jbl"]),
    ("Bose", ["bose"]),
    ("Sennheiser", ["sennheiser", "senheiser", "senneheiser"]),
    ("Skullcandy", ["skullcandy", "skull candy"]),
    ("Jabra", ["jabra"]),
    ("Boult", ["boult audio", "boult"]),
    ("Mivi", ["mivi"]),
    ("Portronics", ["portronics"]),
    ("Zebronics", ["zebronics", "zeb"]),

    # Computing / Laptops / Components
    ("HP", ["hp", "hewlett packard", "pavilion", "omen", "victus"]),
    ("Dell", ["dell", "deil", "alienware", "inspiron", "vostro", "xps"]),
    ("Lenovo", ["lenovo", "lenova", "thinkpad", "ideapad", "legion", "loq"]),
    ("ASUS", ["asus", "assu", "rog", "tuf", "zenbook", "vivobook"]),
    ("Acer", ["acer", "predator", "nitro", "aspire", "swift"]),
    ("MSI", ["msi"]),
    ("LG", ["lg", "gram"]),
    ("Logitech", ["logitech", "logi"]),
    ("Razer", ["razer"]),
    ("Corsair", ["corsair"]),

    # Cameras
    ("Canon", ["canon"]),
    ("Nikon", ["nikon"]),
    ("GoPro", ["gopro", "go pro"]),

    # Appliances
    ("Whirlpool", ["whirlpool"]),
    ("Haier", ["haier"]),
    ("Godrej", ["godrej"]),
    ("Voltas", ["voltas"]),
    ("Daikin", ["daikin"]),
    ("Lloyd", ["lloyd"]),
    ("Blue Star", ["blue star", "bluestar"]),
    ("Prestige", ["prestige"]),
    ("Hawkins", ["hawkins"]),
    ("Pigeon", ["pigeon"]),
    ("Bajaj", ["bajaj"]),
    ("Havells", ["havells"]),
    ("Crompton", ["crompton"]),
    ("Philips", ["philips"]),
    ("Usha", ["usha"]),
    ("V-Guard", ["v-guard", "vguard"]),
    ("IFB", ["ifb"]),
    ("Bosch", ["bosch"]),

    # Beauty & Personal Care
    ("Patanjali", ["patanjali"]),
    ("Himalaya", ["himalaya"]),
    ("Dabur", ["dabur"]),
    ("Mamaearth", ["mamaearth", "mama earth"]),
    ("Plum", ["plum"]),
    ("Wow", ["wow skin science", "wow"]),
    ("mCaffeine", ["mcaffeine", "m caffeine"]),
    ("Nykaa", ["nykaa"]),
    ("Minimalist", ["minimalist", "be minimalist"]),
    ("L'Oreal", ["loreal", "l'oreal", "l oreal"]),
    ("Maybelline", ["maybelline"]),
    ("Lakme", ["lakme"]),

    # Sports
    ("Decathlon", ["decathlon", "quechua", "domyos", "kalenji"]),
    ("Cosco", ["cosco"]),
    ("Nivia", ["nivia"]),
    ("SG", ["sg cricket", "sg"]),
    ("Yonex", ["yonex"]),
]


def _clean_alphanumeric(s: str) -> str:
    """Strip all whitespace and punctuation, keeping lowercase alphanumeric."""
    return re.sub(r'[^a-z0-9]', '', s.lower())


_BRAND_EXCLUSION_WORDS: set[str] = {
    'what', 'should', 'buy', 'between', 'and', 'or', 'under', 'above',
    'below', 'from', 'to', 'with', 'without', 'show', 'suggest',
    'recommend', 'best', 'top', 'good', 'cheap', 'give', 'me',
    'something', 'anything', 'the', 'for', 'a', 'an', 'in', 'of', 'i', 'you',
    'want', 'need', 'is', 'are', 'it', 'this', 'that', 'how', 'much',
    'price', 'rate', 'cost', 'where', 'can', 'find', 'which', 'one', 'two',
    'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'look', 'looking', 'please', 'tell', 'help', 'some', 'any', 'about'
}


class BrandRegistry:
    """
    Extensible Brand Registry supporting exact phrase lookup,
    normalized alphanumeric key resolution, and RapidFuzz token matching.
    """
    def __init__(self, brand_defs: list[tuple[str, list[str]]]):
        self.canonical_list: list[str] = []
        self.alias_to_canonical: dict[str, str] = {}
        self.norm_to_canonical: dict[str, str] = {}
        self.fuzzy_search_keys: list[str] = []

        for canonical, aliases in brand_defs:
            self.canonical_list.append(canonical)
            # Register canonical lower
            c_lower = canonical.lower()
            self.alias_to_canonical[c_lower] = canonical
            self.norm_to_canonical[_clean_alphanumeric(canonical)] = canonical

            for alias in aliases:
                a_lower = alias.lower().strip()
                self.alias_to_canonical[a_lower] = canonical
                norm_key = _clean_alphanumeric(a_lower)
                if norm_key:
                    self.norm_to_canonical[norm_key] = canonical
                # Only include aliases >= 4 chars without stop words in fuzzy search
                if len(norm_key) >= 4 and not any(w in _BRAND_EXCLUSION_WORDS for w in a_lower.split()):
                    self.fuzzy_search_keys.append(a_lower)

        # Sort alias keys by length descending for greedy phrase matching
        self.sorted_aliases = sorted(self.alias_to_canonical.keys(), key=len, reverse=True)
        self.fuzzy_search_keys = sorted(set(self.fuzzy_search_keys), key=len, reverse=True)

    def add_brand(self, canonical: str, aliases: list[str]):
        """Dynamically add new brands without rebuilding the system."""
        self.canonical_list.append(canonical)
        c_lower = canonical.lower()
        self.alias_to_canonical[c_lower] = canonical
        self.norm_to_canonical[_clean_alphanumeric(canonical)] = canonical
        for alias in aliases:
            a_lower = alias.lower().strip()
            self.alias_to_canonical[a_lower] = canonical
            norm_key = _clean_alphanumeric(a_lower)
            if norm_key:
                self.norm_to_canonical[norm_key] = canonical
            if len(norm_key) >= 4 and not any(w in _BRAND_EXCLUSION_WORDS for w in a_lower.split()):
                self.fuzzy_search_keys.append(a_lower)
        self.sorted_aliases = sorted(self.alias_to_canonical.keys(), key=len, reverse=True)
        self.fuzzy_search_keys = sorted(set(self.fuzzy_search_keys), key=len, reverse=True)

    def resolve_all(self, text: str) -> tuple[str, list[str], float, dict]:
        """
        Identify ALL canonical brands in text (for comparison or single-brand queries).
        Returns:
            (modified_text, list_of_canonical_brands, confidence_score, {original_phrase: canonical})
        """
        lower = text.lower()
        corrections = {}
        detected_brands: list[str] = []
        modified = text
        scores: list[float] = []

        # ── Tier 1: Exact alias phrase matches (longest first, non-overlapping) ──
        for alias in self.sorted_aliases:
            if len(alias) <= 2:
                pattern = r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])'
            else:
                pattern = r'\b' + re.escape(alias) + r'\b'

            if re.search(pattern, lower):
                canonical = self.alias_to_canonical[alias]
                if canonical not in detected_brands:
                    detected_brands.append(canonical)
                    corrections[alias] = canonical
                    scores.append(1.0)
                    modified = re.sub(pattern, canonical, modified, flags=re.I)
                    # Mask out the matched alias in lower to avoid sub-matching
                    lower = re.sub(pattern, ' ' * len(alias), lower)

        # ── Tier 2: Normalized alphanumeric token match ──
        words = lower.split()
        for n in (4, 3, 2, 1):
            for i in range(len(words) - n + 1):
                chunk = ' '.join(words[i:i+n])
                norm_chunk = _clean_alphanumeric(chunk)
                if len(norm_chunk) < 4 and n > 1:
                    continue
                if len(norm_chunk) >= 3 and norm_chunk in self.norm_to_canonical:
                    if norm_chunk in _BRAND_EXCLUSION_WORDS:
                        continue
                    canonical = self.norm_to_canonical[norm_chunk]
                    if canonical not in detected_brands:
                        detected_brands.append(canonical)
                        corrections[chunk] = canonical
                        scores.append(0.98)
                        pattern = r'\b' + re.escape(chunk) + r'\b'
                        modified = re.sub(pattern, canonical, modified, count=1, flags=re.I)
                        if modified == text:
                            modified = text.replace(chunk, canonical, 1)

        # ── Tier 3: RapidFuzz matching for misspelled brands ──
        if _RAPIDFUZZ_AVAILABLE and self.fuzzy_search_keys:
            words_mod = modified.lower().split()
            for n in (3, 2, 1):
                for i in range(len(words_mod) - n + 1):
                    chunk_words = words_mod[i:i+n]
                    if any(w in _BRAND_EXCLUSION_WORDS or w in _CATEGORY_VOCAB_SET or w in _COLOR_SET for w in chunk_words):
                        continue

                    chunk = ' '.join(chunk_words)
                    norm_chunk = _clean_alphanumeric(chunk)
                    if len(norm_chunk) < 4 or norm_chunk.isdigit():
                        continue

                    scorer = _rf_fuzz.ratio if n == 1 else _rf_fuzz.token_sort_ratio
                    result = _rf_process.extractOne(
                        chunk,
                        self.fuzzy_search_keys,
                        scorer=scorer,
                        score_cutoff=85,
                    )
                    if result:
                        matched_alias, score, _ = result
                        norm_matched = _clean_alphanumeric(matched_alias)
                        if abs(len(norm_chunk) - len(norm_matched)) > 2:
                            continue

                        canonical = self.alias_to_canonical[matched_alias]
                        if canonical not in detected_brands:
                            detected_brands.append(canonical)
                            corrections[chunk] = canonical
                            pattern = r'\b' + re.escape(chunk) + r'\b'
                            modified = re.sub(pattern, canonical, modified, count=1, flags=re.I)
                            if modified == text:
                                modified = text.replace(chunk, canonical, 1)
                            scores.append(round(score / 100.0, 2))

        avg_conf = round(sum(scores) / len(scores), 2) if scores else 0.0
        return modified, detected_brands, avg_conf, corrections

    def resolve(self, text: str) -> tuple[str, str | None, float, dict]:
        """
        Identify first brand in text (backward compatibility).
        """
        mod, brands, conf, corrs = self.resolve_all(text)
        return mod, (brands[0] if brands else None), conf, corrs


BRAND_REGISTRY = BrandRegistry(_RAW_BRAND_DEFINITIONS)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CATEGORY & AUDIO TYPE VOCABULARY
# ═══════════════════════════════════════════════════════════════════════════════

# Audio-type patterns are deterministic and authoritative.
# Audio types NEVER cross-contaminate.
_STRICT_AUDIO_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('neckband',   re.compile(r'\b(?:neck\s*band|neckband|neckbnd)\b', re.I)),
    ('earbuds',    re.compile(r'\b(?:earbuds?|tws|airpods?|airdopes?|true\s+wireless|buds?|eardbuds?|erbuds?|earbdus?)\b', re.I)),
    ('earphones',  re.compile(r'\b(?:earphones?|wired\s+earphones?|iem|earphon|in[\s-]?ear\s+(?:earphones?|earphon))\b', re.I)),
    ('headphones', re.compile(r'\b(?:headphones?|over[\s-]?ear|on[\s-]?ear|headset|headphon)\b', re.I)),
    ('speaker',    re.compile(r'\b(?:speakers?|bluetooth\s+speaker|soundbar|home\s+theatre|speker)\b', re.I)),
]

# Standard product category patterns
_PRODUCT_CATEGORY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('laptop',          re.compile(r'\b(?:laptops?|notebooks?|ultrabooks?|chromebooks?|macbooks?|laptoop|laptopp|labtop)\b', re.I)),
    ('phone',           re.compile(r'\b(?:phones?|mobiles?|smartphones?|iphones?|phon|mobi)\b', re.I)),
    ('smartwatch',      re.compile(r'\b(?:smartwatch(?:es)?|smart\s*watch(?:es)?|fitness\s+band|smart\s*band|wearable)\b', re.I)),
    ('shoes',           re.compile(r'\b(?:shoes?|sneakers?|footwear|running\s+shoes?|sports\s+shoes?|loafers?|sandals?|snikers)\b', re.I)),
    ('t-shirt',         re.compile(r'\b(?:t[\s-]?shirts?|tees?|polo\s+shirts?|tshirt)\b', re.I)),
    ('shirt',           re.compile(r'\b(?:formal\s+shirts?|casual\s+shirts?|(?<!t[\s-])shirts?)\b', re.I)),
    ('jeans',           re.compile(r'\b(?:jeans?|denims?)\b', re.I)),
    ('watch',           re.compile(r'\b(?:watch(?:es)?|wrist\s*watch(?:es)?)\b', re.I)),
    ('tablet',          re.compile(r'\b(?:tablets?|ipads?|tabs?)\b', re.I)),
    ('camera',          re.compile(r'\b(?:cameras?|dslrs?|mirrorless|camra|gopros?)\b', re.I)),
    ('refrigerator',    re.compile(r'\b(?:refrigerators?|fridges?)\b', re.I)),
    ('washing machine', re.compile(r'\b(?:washing\s+machines?|washers?)\b', re.I)),
    ('air conditioner', re.compile(r'\b(?:air\s*conditioners?|split\s+ac|window\s+ac|\bac\b)\b', re.I)),
    ('television',      re.compile(r'\b(?:televisions?|tvs?|smart\s+tv|led\s+tv)\b', re.I)),
    ('bag',             re.compile(r'\b(?:bags?|backpacks?)\b', re.I)),
]

# Canonical category vocabulary for typo matching
_CATEGORY_VOCAB: list[str] = [
    "laptop", "phone", "earbuds", "earphones", "headphones", "neckband",
    "speaker", "smartwatch", "shoes", "t-shirt", "shirt", "jeans", "watch",
    "tablet", "camera", "refrigerator", "washing machine", "air conditioner",
    "television", "bag"
]
_CATEGORY_VOCAB_SET: set[str] = set(_CATEGORY_VOCAB)

# Word-level typo correction lookup for category & common terms
_COMMON_TYPO_MAP: dict[str, str] = {
    "laptoop":     "laptop",
    "laptopp":     "laptop",
    "labtop":      "laptop",
    "eardbuds":    "earbuds",
    "eardbud":     "earbuds",
    "erbuds":      "earbuds",
    "earbdus":     "earbuds",
    "camra":       "camera",
    "wirless":     "wireless",
    "wirelss":     "wireless",
    "bluethooth":  "bluetooth",
    "blutooth":    "bluetooth",
    "gamng":       "gaming",
    "gamin":       "gaming",
    "snikers":     "sneakers",
    "battry":      "battery",
    "batry":       "battery",
    "prcessor":    "processor",
    "speker":      "speaker",
    "compre":      "compare",
    "comapre":     "compare",
    "compair":     "compare",
    "v/s":         "vs",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. COLOR NORMALIZATION WITH STRICT TOKEN BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════════

# Multi-word colors handled first with strict word boundaries
_MULTI_WORD_COLORS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bnavy\s*blu(?:e)?\b', re.I), "navy blue"),
    (re.compile(r'\bsky\s*blu(?:e)?\b',  re.I), "sky blue"),
    (re.compile(r'\boff\s*wht\b|\boff\s*white\b', re.I), "off white"),
    (re.compile(r'\bdark\s*green\b', re.I), "dark green"),
    (re.compile(r'\blight\s*blue\b', re.I), "light blue"),
    (re.compile(r'\bdark\s*blue\b',  re.I), "dark blue"),
]

# Single-word color aliases with STRICT \b word boundaries
_SINGLE_COLOR_ALIASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(?:blu|bleu)\b', re.I), "blue"),
    (re.compile(r'\b(?:blk|blck|blac)\b', re.I), "black"),
    (re.compile(r'\b(?:wht|whit)\b', re.I), "white"),
    (re.compile(r'\b(?:gry|grey)\b', re.I), "gray"),
    (re.compile(r'\bgrn\b', re.I), "green"),
    (re.compile(r'\b(?:ylw|yello)\b', re.I), "yellow"),
    (re.compile(r'\b(?:prple|purpl)\b', re.I), "purple"),
    (re.compile(r'\b(?:org|orng)\b', re.I), "orange"),
    (re.compile(r'\b(?:brwn|brn)\b', re.I), "brown"),
    (re.compile(r'\bmaron\b', re.I), "maroon"),
    (re.compile(r'\b(?:silv|silvr)\b', re.I), "silver"),
    (re.compile(r'\bgld\b', re.I), "gold"),
    (re.compile(r'\b(?:olvie|oliv)\b', re.I), "olive"),
    (re.compile(r'\blavndr\b', re.I), "lavender"),
]

# Canonical single-word colors (must match as whole words)
_CANONICAL_COLORS: list[str] = [
    "red", "blue", "green", "black", "white", "pink", "yellow", "purple",
    "orange", "gray", "silver", "gold", "brown", "navy", "beige",
    "maroon", "cream", "olive", "teal", "coral", "khaki", "lavender", "turquoise"
]
_COLOR_SET: set[str] = set(_CANONICAL_COLORS) | {"navy blue", "sky blue", "off white", "dark green", "light blue", "dark blue"}


def _normalize_colors(text: str) -> tuple[str, str | None, float]:
    """
    Safely normalizes color variations using strict token boundaries.
    Prevents 'bluetooth' -> 'blue' and 'card' -> 'red'.
    Returns:
        (text_with_normalized_color, canonical_color_or_None, confidence)
    """
    detected_color: str | None = None
    conf = 0.0
    modified = text

    # Step 1: Multi-word colors
    for pattern, canonical in _MULTI_WORD_COLORS:
        if pattern.search(modified):
            detected_color = canonical
            conf = 1.0
            modified = pattern.sub(canonical, modified)
            return modified, detected_color, conf

    # Step 2: Single-word abbreviations/aliases (with strict boundaries)
    for pattern, canonical in _SINGLE_COLOR_ALIASES:
        if pattern.search(modified):
            detected_color = canonical
            conf = 0.95
            modified = pattern.sub(canonical, modified)
            return modified, detected_color, conf

    # Step 3: Canonical colors
    for color in sorted(_CANONICAL_COLORS, key=len, reverse=True):
        pat = re.compile(r'\b' + re.escape(color) + r'\b', re.I)
        if pat.search(modified):
            detected_color = color
            conf = 1.0
            break

    return modified, detected_color, conf


# ═══════════════════════════════════════════════════════════════════════════════
# 4. MULTI-DOMAIN SPECIFICATION & CONFIGURATION EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Extensible specification patterns across categories
_SPEC_RULES: list[tuple[str, list[tuple[re.Pattern, Any]]]] = [
    # ── Laptop / Desktop / Generic Computing ──
    ("cpu", [
        # Intel Core models: i5-12400, i7 13700H, Core Ultra 7
        (re.compile(r'\b(?:intel\s+core\s+)?(i[3579][-\s]?\d{4,5}\w*)\b', re.I), lambda m: m.group(1).upper().replace(' ', '-')),
        # Core Ultra
        (re.compile(r'\b(?:core\s+ultra\s+[579])\b', re.I), lambda m: m.group(0).title()),
        # Bare i3/i5/i7/i9 (using negative lookahead for 4-5 digit model numbers only)
        (re.compile(r'\b(i[3579])\b(?!\s*[-]?\d{4,5})', re.I), lambda m: m.group(1).lower()),
        # AMD Ryzen models
        (re.compile(r'\b(?:amd\s+)?(ryzen\s*[3579]\s*(?:\d{4}\w*)?)\b', re.I), lambda m: m.group(1).title()),
        # Apple Silicon M-series
        (re.compile(r'\b(m[1234]\s*(?:pro|max|ultra)?)\b', re.I), lambda m: m.group(1).upper()),
        # Mobile Chipsets
        (re.compile(r'\b(snapdragon\s*(?:\d+\w*|\d+\s*gen\s*\d|\w+))\b', re.I), lambda m: m.group(1).title()),
        (re.compile(r'\b(dimensity\s*\d+\w*)\b', re.I), lambda m: m.group(1).title()),
        (re.compile(r'\b(bionic\s*a\d+)\b', re.I), lambda m: m.group(1).title()),
        (re.compile(r'\b(tensor\s*g\d+)\b', re.I), lambda m: m.group(1).title()),
        (re.compile(r'\b(exynos\s*\d+\w*)\b', re.I), lambda m: m.group(1).title()),
    ]),

    ("gpu", [
        # NVIDIA RTX / GTX with model number
        (re.compile(r'\b(rtx\s*\d{3,4}\w*)\b', re.I), lambda m: m.group(1).upper().replace(' ', '')),
        (re.compile(r'\b(gtx\s*\d{3,4}\w*)\b', re.I), lambda m: m.group(1).upper().replace(' ', '')),
        # AMD Radeon RX
        (re.compile(r'\b(rx\s*\d{3,4}\w*)\b', re.I), lambda m: m.group(1).upper().replace(' ', '')),
        # RTX / GTX general
        (re.compile(r'\b(?:rtx\s*graphics?|rtx\s*gpu|rtx)\b', re.I), lambda m: 'RTX'),
        (re.compile(r'\b(?:gtx\s*graphics?|gtx\s*gpu|gtx)\b', re.I), lambda m: 'GTX'),
        # Intel Arc
        (re.compile(r'\b(arc\s*[a-z]?\d{3})\b', re.I), lambda m: m.group(1).upper()),
        # Dedicated graphics phrases (handles graphic card, graphics card, dedicated graphics, dedicated gpu, etc.)
        (re.compile(r'\b(?:dedicated\s*(?:graphics?|gpu|cards?)?|discrete\s*(?:graphics?|gpu)?|graphics?\s*cards?|with\s*graphics?)\b', re.I), lambda m: 'dedicated'),
        (re.compile(r'\b(?:graphics?|gpu)\b', re.I), lambda m: 'dedicated'),
    ]),

    ("ram", [
        # Explicit RAM with unit: 16gb ram, 8 gb lpddr5, 32gb ddr4
        (re.compile(r'\b(\d+)\s*gb\s*(?:ram|lpddr\d?|ddr\d?|memory)\b', re.I), lambda m: f"{m.group(1)}GB"),
        # Standalone "16gb" or "8gb" when not followed by storage keywords
        (re.compile(r'\b(\d+)\s*gb\b(?!\s*(?:ssd|hdd|rom|storage|emmc|nvme|internal))', re.I),
         lambda m: f"{m.group(1)}GB" if int(m.group(1)) in (2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64) else None),
    ]),

    ("storage", [
        # Explicit storage with SSD/HDD/ROM
        (re.compile(r'\b(\d+)\s*(gb|tb)\s*(ssd|hdd|nvme|emmc|storage|rom|internal)\b', re.I),
         lambda m: f"{m.group(1)}{m.group(2).upper()} {m.group(3).upper() if m.group(3).upper() in ('SSD','HDD','NVME') else ''}".strip()),
        # TB Storage: 1tb, 2tb
        (re.compile(r'\b(\d+)\s*tb\b', re.I), lambda m: f"{m.group(1)}TB SSD"),
        # Standalone storage numbers: 512 ssd, 256 ssd, 512gb ssd
        (re.compile(r'\b(128|256|512|1024|2048)\s*(?:gb\s*)?(ssd|hdd|storage)\b', re.I),
         lambda m: f"{m.group(1)}GB {m.group(2).upper()}"),
    ]),

    ("display", [
        (re.compile(r'\b(\d+\.?\d*)["\']?\s*(?:inch|display|screen)\b', re.I), lambda m: f"{m.group(1)} inch"),
        (re.compile(r'\b(fhd|qhd|4k|amoled|oled|ips|120hz|144hz|165hz|240hz|90hz)\b', re.I), lambda m: m.group(1).upper()),
    ]),

    # ── Phone Specific ──
    ("camera", [
        (re.compile(r'\b(\d+)\s*(?:mp|mega\s*pixel)\b', re.I), lambda m: f"{m.group(1)}MP"),
        (re.compile(r'\b(triple|quad|dual)\s*camera\b', re.I), lambda m: f"{m.group(1).lower()} camera"),
        (re.compile(r'\b(?:good|best|great|clear)\s*cam(?:era)?\b', re.I), lambda m: "good camera"),
    ]),

    ("battery", [
        (re.compile(r'\b(\d{4,5})\s*mah\b', re.I), lambda m: f"{m.group(1)}mAh"),
        (re.compile(r'\b(\d+)\s*(?:hours?|hrs?|h)\s*(?:battery|playtime|backup)\b', re.I), lambda m: f"{m.group(1)} hours"),
        (re.compile(r'\b(?:good|long|big|best)\s*battery\b', re.I), lambda m: "good battery"),
    ]),

    # ── Audio Specific ──
    ("anc", [
        (re.compile(r'\b(?:anc|active\s+noise\s+cancel(?:l?ation|ling)?|noise\s+cancel(?:l?ation|ling)?)\b', re.I), lambda m: "ANC"),
        (re.compile(r'\b(?:enc|environmental\s+noise\s+cancel(?:l?ation|ling)?)\b', re.I), lambda m: "ENC"),
    ]),

    ("bluetooth", [
        (re.compile(r'\bbluetooth\s*(?:v?([\d.]+))?\b', re.I), lambda m: f"Bluetooth {m.group(1)}" if m.group(1) else "Bluetooth"),
        (re.compile(r'\bbt\s*(v?[\d.]+)\b', re.I), lambda m: f"Bluetooth {m.group(1)}"),
    ]),

    ("wireless", [
        (re.compile(r'\b(?:true\s+wireless|wireless|tws)\b', re.I), lambda m: "wireless"),
        (re.compile(r'\bwired\b', re.I), lambda m: "wired"),
    ]),
]


def _extract_specifications(text: str) -> dict[str, str]:
    """Extract hardware specifications from query text."""
    specs: dict[str, str] = {}
    lower = text.lower()

    for spec_name, rules in _SPEC_RULES:
        if spec_name in specs:
            continue
        for pattern, normalizer in rules:
            m = pattern.search(lower)
            if m:
                val = normalizer(m) if normalizer else m.group(0).strip()
                if val:
                    specs[spec_name] = str(val)
                    break

    # Contextual check for bare "512 ssd" or "512" near laptop context
    if "storage" not in specs:
        m = re.search(r'\b(128|256|512|1024)\b(?=\s*(?:ssd|hdd|gb|storage|laptop|pc|phone))', lower)
        if m:
            unit = "GB SSD" if "ssd" in lower else "GB"
            specs["storage"] = f"{m.group(1)}{unit}"

    return specs


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PRICE RANGE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_price_range(text: str) -> dict[str, int | None]:
    """
    Extract budget constraints (min and max) in INR.
    Supports: under 50k, below 30,000, between 20k and 30k, above 15k, under 2k.
    """
    price = {"min": None, "max": None}
    lower = text.lower()

    # Range pattern: "between 20k and 30k" / "20k to 30k" / "20000 - 30000"
    m_range = re.search(
        r'(?:between|from)?\s*[₹₨$rs\.]*\s*(\d[\d,]*)\s*(k\b|thousand\b)?\s*(?:to|and|-)\s*[₹₨$rs\.]*\s*(\d[\d,]*)\s*(k\b|thousand\b)?',
        lower
    )
    if m_range:
        v1 = int(m_range.group(1).replace(',', ''))
        if m_range.group(2) or v1 < 100:  # e.g. 20 -> 20k
            v1 *= 1000
        v2 = int(m_range.group(3).replace(',', ''))
        if m_range.group(4) or v2 < 100:
            v2 *= 1000
        price["min"] = min(v1, v2)
        price["max"] = max(v1, v2)
        return price

    # Max price: under / below / less than / upto / max / budget of / within
    m_max = re.search(
        r'(?:under|below|less\s+than|upto?|up\s+to|within|max(?:imum)?|budget\s+of?|around)'
        r'\s*[₹₨$rs\.]*\s*(\d[\d,]*)\s*(k\b|thousand\b)?',
        lower
    )
    if m_max:
        val = int(m_max.group(1).replace(',', ''))
        if m_max.group(2) or (val < 100 and 'k' in m_max.group(0).lower()):
            val *= 1000
        price["max"] = val

    # Min price: above / over / more than / starting from / min / at least
    m_min = re.search(
        r'(?:above|over|more\s+than|min(?:imum)?|at\s+least|starting\s+from)'
        r'\s*[₹₨$rs\.]*\s*(\d[\d,]*)\s*(k\b|thousand\b)?',
        lower
    )
    if m_min:
        val = int(m_min.group(1).replace(',', ''))
        if m_min.group(2) or (val < 100 and 'k' in m_min.group(0).lower()):
            val *= 1000
        price["min"] = val

    return price


# ═══════════════════════════════════════════════════════════════════════════════
# 6. USE-CASE & INTENT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

_USE_CASE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('gaming',   re.compile(r'\b(?:gaming|games?|gamer|esports)\b', re.I)),
    ('coding',   re.compile(r'\b(?:coding|programming|develop(?:er|ment)?|software|coding\s+and\s+gaming)\b', re.I)),
    ('office',   re.compile(r'\b(?:office|work|professional|business|workplace)\b', re.I)),
    ('music',    re.compile(r'\b(?:music|sound\s+quality|bass|listening|audiophile)\b', re.I)),
    ('travel',   re.compile(r'\b(?:travel|portable|on\s+the\s+go|commute)\b', re.I)),
    ('gym',      re.compile(r'\b(?:gym|workout|fitness|running|exercise)\b', re.I)),
    ('study',    re.compile(r'\b(?:study|students?|college|school)\b', re.I)),
    ('photo',    re.compile(r'\b(?:photography|photos?|vlog(?:ging)?|videography)\b', re.I)),
]


def _detect_use_case(text: str) -> str | None:
    for uc, pattern in _USE_CASE_PATTERNS:
        if pattern.search(text):
            return uc
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 7. HARD VS SOFT REQUIREMENTS CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_requirements(
    category: str | None,
    brand: str | None,
    color: str | None,
    price: dict[str, int | None],
    specs: dict[str, str],
    use_case: str | None,
    original_text: str,
) -> tuple[list[str], list[str]]:
    """
    Classifies requirements according to strict rules:
      - HARD: Explicit user constraints (category, brand, color, price, explicit hardware specs)
      - SOFT: Subjective or qualitative preferences (good for gaming, good camera, best battery)
    """
    hard: list[str] = []
    soft: list[str] = []
    lower = original_text.lower()

    # Category is ALWAYS hard when present
    if category:
        hard.append(f"category: {category}")

    # Brand is ALWAYS hard when present
    if brand:
        if isinstance(brand, list):
            for b in brand:
                hard.append(f"brand: {b}")
        else:
            hard.append(f"brand: {brand}")

    # Color is ALWAYS hard when present
    if color:
        hard.append(f"color: {color}")

    # Price constraints are ALWAYS hard
    if price.get("max") is not None:
        hard.append(f"price <= {price['max']}")
    if price.get("min") is not None:
        hard.append(f"price >= {price['min']}")

    # Hardware Specifications:
    # Explicit specs (i5, 16GB, 512GB SSD, dedicated GPU, 5000mAh, ANC) are HARD.
    # Qualitative specs (good camera, good battery) are SOFT unless framed mandatorily.
    for spec_name, val in specs.items():
        spec_entry = f"{spec_name}: {val}"
        is_qualitative = val in ("good camera", "good battery", "clear camera")
        is_mandatory = bool(re.search(r'\b(?:must|need|strictly|mandatory|require[sd]?)\b', lower))

        if is_qualitative and not is_mandatory:
            soft.append(spec_entry)
        else:
            hard.append(spec_entry)

    # Use-case:
    # Subjective suitability (good for gaming, for coding) is SOFT unless explicitly mandatory
    if use_case:
        uc_entry = f"use_case: {use_case}"
        is_mandatory = bool(re.search(r'\b(?:strictly\s+for|only\s+for|must\s+be\s+for|need\s+for)\s+' + re.escape(use_case), lower))
        if is_mandatory:
            hard.append(uc_entry)
        else:
            soft.append(uc_entry)

    return hard, soft


# ═══════════════════════════════════════════════════════════════════════════════
# 8. STRUCTURED QUERY OBJECT (PHASE 1 OUTPUT)
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# 7b. INTENT + SEARCH_REQUIRED PRE-CLASSIFIER (Deterministic, No LLM)
# ═══════════════════════════════════════════════════════════════════════════════

# Signals that the user explicitly does NOT want product search
_NO_SEARCH_SIGNALS = re.compile(
    r'\b(?:just\s+(?:explain|tell|compare|say|show|answer)|'
    r'only\s+(?:explain|tell|compare|answer)|'
    r"don'?t\s+(?:recommend|show|search|find)|'"
    r'no\s+products?|text\s+only|just\s+info|'
    r'explain\s+the\s+difference|'
    r'without\s+(?:products?|links?|cards?))\b',
    re.I,
)

# Signals that the user explicitly WANTS product results
_SEARCH_SIGNALS = re.compile(
    r'\b(?:show\s+me|find\s+me|give\s+me|get\s+me|'
    r'recommend|suggest|buy|purchase|order|'
    r'available|in\s+stock|products?|listings?|'
    r'where\s+can\s+i\s+(?:buy|get|find)|'
    r'price|under\s*[₹₨$]?\s*\d|below\s*[₹₨$]?\s*\d|'
    r'within\s*[₹₨$]?\s*\d|upto?\s*[₹₨$]?\s*\d|'
    r'around\s*[₹₨$]?\s*\d)\b',
    re.I,
)
# Information-seeking patterns
_INFO_PATTERNS = re.compile(
    r'^\s*(?:what\s+is|what\s+are|explain|how\s+does|'
    r'tell\s+me\s+about|what\s+does|define|meaning\s+of|'
    r'how\s+(?:to|do|does)|why\s+(?:is|are|does)|'
    r'what\s+should\s+i\s+(?:look\s+for|check|consider|know)|'
    r'what\s+to\s+(?:look\s+for|check|consider|know)|'
    r'how\s+to\s+choose)\b',
    re.I,
)
# Strong comparison patterns — definitive brand/product comparison signals
_COMPARISON_STRONG = re.compile(
    r'\bvs\.?\b|\bversus\b|\bcompare\b|\bcomparison\b|\bcompre\b|\bcomapre\b|'
    r'\bdifference\s+between\b|'
    r'\bwhich\s+(?:\w+\s+)?(?:is\s+)?(?:best|better)\s+(?:\w+\s+)?(?:or|between|vs)\b|'
    r'\b(?:\w+\s+or\s+\w+)\b',
    re.I,
)

# Weak comparison patterns — can also indicate info/concept questions when no brands present
_COMPARISON_WEAK = re.compile(
    r'\bwhich\s+is\s+better\b|\bbetter\s+than\b|\bis\s+\w+\s+better\b',
    re.I,
)

# Combined — for backward compat
_COMPARISON_PATTERNS = re.compile(
    r'\bvs\.?\b|\bversus\b|\bcompare\b|\bcomparison\b|\bcompre\b|'
    r'\bwhich\s+is\s+better\b|\bbetter\s+than\b|\bis\s+\w+\s+better\b|'
    r'\bdifference\s+between\b',
    re.I,
)

# Product/brand nouns — used to distinguish concept questions from product comparisons
_PRODUCT_BRAND_RE = re.compile(
    r'\b(?:phone|laptop|mobile|earbuds?|earphones?|headphones?|tablet|camera|'
    r'watch|tv|shirt|jeans|shoes?|speaker|smartwatch|refrigerator|ac|cooler|'
    r'cooker|bag|sneakers?|headset|neckband|monitor|keyboard|mouse|printer|'
    r'router|charger|powerbank|dslr|mirrorless|'
    r'nike|adidas|samsung|apple|oneplus|realme|vivo|oppo|sony|jbl|boat|bose|'
    r'hp|dell|lenovo|asus|acer|msi|lg|xiaomi|motorola|google|nothing)\b',
    re.I,
)

# Recommendation patterns
_RECOMMENDATION_PATTERNS = re.compile(
    r'\b(?:best|top|good|great|recommend(?:ation)?|'
    r'which\s+(?:is|are|should)|what\s+should\s+i\s+(?:buy|get|choose)|'
    r'suggest(?:ion)?|advise?)\b',
    re.I,
)


def _detect_intent_signals(text: str, detected_brands: list[str] | None = None) -> tuple[str | None, bool | None]:
    """
    Deterministic pre-classifier: returns (intent_hint, search_required_hint).
    Both may be None if the signal is ambiguous — chatbot.py will resolve with LLM.
    Priority: explicit user instructions > structural signals.
    """
    lower = text.lower()
    has_price = bool(re.search(r'(?:under|below|upto?|within|around)\s*[₹₨$]?\s*\d', lower))
    has_product_or_brand = bool(_PRODUCT_BRAND_RE.search(text)) or bool(detected_brands)

    # ── Explicit no-search instruction (wins over everything) ──────────────────
    if _NO_SEARCH_SIGNALS.search(text):
        if _COMPARISON_PATTERNS.search(text) or (detected_brands and len(detected_brands) >= 2):
            return 'comparison', False
        return 'information', False

    # ── Information queries (what is / explain / how does) ─────────────────────
    if _INFO_PATTERNS.search(text) and not _SEARCH_SIGNALS.search(text):
        return 'information', False

    # ── Multi-brand comparison signal (2+ brands detected in query) ────────────
    # E.g. "which laptop is best hp or dell", "compare nike and adidas", "hp or dell"
    if detected_brands and len(detected_brands) >= 2:
        search_hint = has_price or bool(_SEARCH_SIGNALS.search(text))
        return 'comparison', search_hint

    # ── Strong comparison signals (vs/compare/X or Y/difference between) ───────
    if _COMPARISON_STRONG.search(text):
        search_hint = has_price or bool(_SEARCH_SIGNALS.search(text))
        return 'comparison', search_hint

    # ── Weak comparison (better than / which is better) ────────────────────────
    # Only treat as comparison if product/brand nouns are present.
    # Otherwise route to information — e.g. "Is OLED better than LCD?" has no
    # brands/products and is a concept question.
    if _COMPARISON_WEAK.search(text):
        if has_product_or_brand:
            search_hint = has_price or bool(_SEARCH_SIGNALS.search(text))
            return 'comparison', search_hint
        else:
            # Concept question without products/brands → information
            return 'information', False

    # ── Recommendation signals (suggest / recommend / best / which is best) ───
    if _RECOMMENDATION_PATTERNS.search(text):
        return 'recommendation', True

    # ── Explicit product search signals (specs/category + price constraint) ────
    if has_price:
        return 'product_search', True

    if _SEARCH_SIGNALS.search(text):
        return 'recommendation', True

    # Ambiguous — let LLM decide
    return None, None


class QueryUnderstanding:
    """
    Structured query representation resulting from the Phase 1 understanding pass.
    """
    __slots__ = (
        'original_query',
        'normalized_query',
        'category',
        'category_confidence',
        'audio_type',
        'brand',
        'brands',
        'brand_confidence',
        'price',
        'specifications',
        'color',
        'color_confidence',
        'use_case',
        'keywords',
        'hard_requirements',
        'soft_preferences',
        'overall_confidence',
        'needs_clarification',
        'clarification_msg',
        'corrected_words',
        'intent',
        'search_required',
    )

    def __init__(self):
        self.original_query: str = ""
        self.normalized_query: str = ""
        self.category: str | None = None
        self.category_confidence: float = 0.0
        self.audio_type: str | None = None
        self.brand: str | list[str] | None = None
        self.brands: list[str] = []
        self.brand_confidence: float = 0.0
        self.price: dict[str, int | None] = {"min": None, "max": None}
        self.specifications: dict[str, str] = {}
        self.color: str | None = None
        self.color_confidence: float = 0.0
        self.use_case: str | None = None
        self.keywords: list[str] = []
        self.hard_requirements: list[str] = []
        self.soft_preferences: list[str] = []
        self.overall_confidence: float = 0.0
        self.needs_clarification: bool = False
        self.clarification_msg: str = ""
        self.corrected_words: dict[str, str] = {}
        # ── Intent fields (set after full understanding pass) ──────────────────
        self.intent: str | None = None           # information|comparison|recommendation|product_search
        self.search_required: bool | None = None  # True|False|None (None = not yet resolved)

    def to_dict(self) -> dict[str, Any]:
        """Return the standard structured query dictionary required for Phase 1."""
        return {
            "intent": self.intent,
            "search_required": self.search_required,
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "category": self.category,
            "category_confidence": self.category_confidence,
            "brand": self.brand,
            "brands": self.brands,
            "brand_confidence": self.brand_confidence,
            "price": self.price,
            "specifications": self.specifications,
            "color": self.color,
            "use_case": self.use_case,
            "keywords": self.keywords,
            "hard_requirements": self.hard_requirements,
            "soft_preferences": self.soft_preferences,
            "overall_confidence": self.overall_confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_msg": self.clarification_msg,
        }

    def explain(self) -> str:
        """Debug helper to format and inspect the understanding pass."""
        lines = [
            "Query Understanding Explanation:",
            "-" * 40,
            f"Original Query      : {self.original_query}",
            f"Normalized Query    : {self.normalized_query}",
            f"Detected Category   : {self.category} (conf: {self.category_confidence:.2f})",
            f"Audio Type          : {self.audio_type}",
            f"Detected Brand      : {self.brand} (conf: {self.brand_confidence:.2f})",
            f"Detected Brands     : {self.brands}",
            f"Detected Colour     : {self.color}",
            f"Detected Specs      : {self.specifications}",
            f"Price Range         : min={self.price.get('min')}, max={self.price.get('max')}",
            f"Use Case            : {self.use_case}",
            f"Hard Requirements   : {self.hard_requirements}",
            f"Soft Preferences    : {self.soft_preferences}",
            f"Overall Confidence  : {self.overall_confidence:.2f}",
            f"Clarification Status: {self.needs_clarification}",
        ]
        if self.corrected_words:
            lines.append(f"Corrected Words     : {self.corrected_words}")
        if self.needs_clarification:
            lines.append(f"Clarification Msg   : {self.clarification_msg}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<QueryUnderstanding category={self.category!r} brand={self.brand!r} "
                f"price={self.price} conf={self.overall_confidence:.2f} clarify={self.needs_clarification}>")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. MAIN UNDERSTANDING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_vocabulary_typo_corrections(text: str) -> tuple[str, dict[str, str]]:
    """
    Safely corrects known typos against category vocabulary.
    Avoids corrupting numbers, model identifiers, or unknown words.
    """
    words = text.split()
    corrected: list[str] = []
    corrections_map: dict[str, str] = {}

    for w in words:
        clean_w = re.sub(r'^[^\w]+|[^\w]+$', '', w).lower()

        # Step 1: Direct common typo map
        if clean_w in _COMMON_TYPO_MAP:
            target = _COMMON_TYPO_MAP[clean_w]
            corrections_map[clean_w] = target
            corrected.append(w.lower().replace(clean_w, target))
            continue

        # Step 2: RapidFuzz matching for category words only (length >= 4, not numbers)
        if _RAPIDFUZZ_AVAILABLE and len(clean_w) >= 4 and not clean_w.isdigit():
            if clean_w not in _CATEGORY_VOCAB_SET and clean_w not in _COLOR_SET:
                res = _rf_process.extractOne(
                    clean_w,
                    _CATEGORY_VOCAB,
                    scorer=_rf_fuzz.WRatio,
                    score_cutoff=85,
                )
                if res:
                    matched_cat, score, _ = res
                    # Only accept high quality matches on longer words
                    if score >= 88:
                        corrections_map[clean_w] = matched_cat
                        corrected.append(w.lower().replace(clean_w, matched_cat))
                        continue

        corrected.append(w)

    return ' '.join(corrected), corrections_map


def understand(query: str) -> QueryUnderstanding:
    """
    Main query understanding entry point.
    Runs the full deterministic normalization, entity extraction, and confidence scoring pipeline.
    """
    qu = QueryUnderstanding()
    raw_query = query.strip()
    qu.original_query = raw_query

    if not raw_query:
        qu.needs_clarification = True
        qu.clarification_msg = "Please tell me what product you are looking for!"
        qu.overall_confidence = 0.0
        return qu

    # ── Step 1: Whitespace cleanup ────────────────────────────────────────────
    current_text = re.sub(r'\s+', ' ', raw_query).strip()

    # ── Step 2: Safe Color Normalization (strict token boundaries) ────────────
    current_text, detected_color, color_conf = _normalize_colors(current_text)
    qu.color = detected_color
    qu.color_confidence = color_conf

    # ── Step 3: Extensible Brand Resolution (Exact -> Normalized -> RapidFuzz) ──
    current_text, detected_brands, brand_conf, brand_corrections = BRAND_REGISTRY.resolve_all(current_text)
    qu.brands = detected_brands
    if len(detected_brands) > 1:
        qu.brand = detected_brands
    elif len(detected_brands) == 1:
        qu.brand = detected_brands[0]
    else:
        qu.brand = None
    qu.brand_confidence = brand_conf
    qu.corrected_words.update(brand_corrections)

    # ── Step 4: Vocabulary-Constrained Typo & Spelling Correction ──────────────
    current_text, vocab_corrections = _apply_vocabulary_typo_corrections(current_text)
    qu.corrected_words.update(vocab_corrections)

    qu.normalized_query = re.sub(r'\s+', ' ', current_text).strip()

    # ── Step 5: Strict Audio-Type Detection (Authoritative) ───────────────────
    # Run against normalized text + original text
    detected_audio = None
    for audio_name, pattern in _STRICT_AUDIO_PATTERNS:
        if pattern.search(qu.normalized_query) or pattern.search(qu.original_query):
            detected_audio = audio_name
            break
    qu.audio_type = detected_audio

    # ── Step 6: Category Resolution ───────────────────────────────────────────
    if detected_audio:
        qu.category = detected_audio
        qu.category_confidence = 1.0
    else:
        for cat_name, pattern in _PRODUCT_CATEGORY_PATTERNS:
            if pattern.search(qu.normalized_query) or pattern.search(qu.original_query):
                qu.category = cat_name
                # Check if it was matched via typo correction
                if any(c == cat_name for c in qu.corrected_words.values()):
                    qu.category_confidence = 0.94
                else:
                    qu.category_confidence = 1.0
                break

    # ── Step 7: Price Extraction ──────────────────────────────────────────────
    qu.price = _extract_price_range(qu.normalized_query)

    # ── Step 8: Specification Extraction ──────────────────────────────────────
    qu.specifications = _extract_specifications(qu.normalized_query)

    # ── Step 9: Use-Case Detection ────────────────────────────────────────────
    qu.use_case = _detect_use_case(qu.normalized_query)

    # ── Step 10: Hard vs Soft Requirements Classification ─────────────────────
    qu.hard_requirements, qu.soft_preferences = _classify_requirements(
        qu.category, qu.brand, qu.color, qu.price, qu.specifications, qu.use_case, qu.original_query
    )

    # ── Step 11: Meaningful Keywords Extraction ───────────────────────────────
    kw_text = qu.normalized_query.lower()
    # Strip known entities from keywords
    remove_patterns = [
        r'\b(?:under|below|less\s+than|upto?|up\s+to|within|max(?:imum)?|budget\s+of?|around)\s*[₹₨$rs\.]*\s*\d[\d,]*\s*(?:k\b|thousand\b)?',
        r'\b\d[\d,]*\s*(?:k\b|thousand\b)?\b',
        r'\b(?:best|top|good|find|show|get|suggest|recommend|i\s+need|i\s+want|looking\s+for|please|for|with|a|an|the|of|in|to)\b',
        r'\bindia\b',
    ]
    for b in qu.brands:
        remove_patterns.append(r'\b' + re.escape(b.lower()) + r'\b')
    if qu.color:
        remove_patterns.append(r'\b' + re.escape(qu.color.lower()) + r'\b')
    if qu.category:
        remove_patterns.append(r'\b' + re.escape(qu.category.lower()) + r'\b')

    for p in remove_patterns:
        kw_text = re.sub(p, ' ', kw_text, flags=re.I)
    kw_text = re.sub(r'\s+', ' ', kw_text).strip()
    qu.keywords = [w for w in kw_text.split() if len(w) > 2]

    # ── Step 12: Overall Confidence Calculation ───────────────────────────────
    # Confidence is grounded in actual entity detection quality:
    conf = 0.0
    if qu.category:
        conf += 0.45 * qu.category_confidence
    if qu.brands:
        conf += 0.25 * qu.brand_confidence
    if qu.price.get("max") is not None or qu.price.get("min") is not None:
        conf += 0.15
    if qu.specifications:
        conf += min(0.20, 0.10 * len(qu.specifications))
    if qu.color:
        conf += 0.10 * qu.color_confidence
    if qu.use_case:
        conf += 0.05

    # Check for gibberish / total absence of valid tokens
    meaningful_tokens = [
        w for w in qu.normalized_query.split()
        if len(w) >= 3 and w.lower() not in (
            'the', 'for', 'and', 'with', 'get', 'best', 'top', 'good', 'new', 'any', 'are', 'show', 'suggest', 'recommend', 'what', 'should', 'buy'
        )
    ]

    # Normalize overall confidence
    qu.overall_confidence = round(min(1.0, conf), 2)

    # ── Step 13: Clarification Decision ───────────────────────────────────────
    # Clarify ONLY if query cannot be identified as any valid product or shopping intent
    if (qu.category is None
            and not qu.brands
            and not qu.specifications
            and qu.overall_confidence < 0.25):
        qu.needs_clarification = True
        qu.clarification_msg = (
            "What type of product are you looking for? For example: laptop, phone, earbuds, shoes, t-shirt, or something else?"
        )

    # ── Step 14: Deterministic intent pre-classification ──────────────────────
    # Provides a baseline hint used by chatbot.py when resolving final intent.
    # chatbot.py will override these with LLM intent when conf >= 0.65.
    intent_hint, search_hint = _detect_intent_signals(raw_query, detected_brands=qu.brands)
    qu.intent = intent_hint
    qu.search_required = search_hint
    print(f"[QU] intent_hint={intent_hint!r} search_required_hint={search_hint}")

    return qu


def understand_and_log(query: str) -> QueryUnderstanding:
    """
    Runs understand() and prints structured debug logs for inspection.
    """
    qu = understand(query)
    print(
        f"[QU] category={qu.category!r} audio={qu.audio_type!r} "
        f"brand={qu.brand!r} color={qu.color!r} price={qu.price} "
        f"specs={qu.specifications} conf={qu.overall_confidence:.2f} "
        f"needs_clarification={qu.needs_clarification}"
    )
    return qu


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Test Runner
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    test_queries = [
        "best laptoop for coding",
        "good eardbuds",
        "best camra phone",
        "wirless earbuds",
        "bluethooth headphones",
        "u s polo shoes",
        "uspolo shirt",
        "samsng phone",
        "real me mobile",
        "fireboltt watch",
        "blu shoes",
        "navy blu t shirt",
        "blk jeans",
        "grey sneakers",
        "i5 16gb 512 ssd laptop",
        "phone with 5000mah battery",
        "earbuds with anc and 40 hours battery",
        "gaming laptop with rtx graphics",
        "under 50k",
        "below ₹30,000",
        "between 20k and 30k",
        "above 15k",
        "i want a blu u s polo shoe under 2k",
        "best laptoop i5 16gb 512 ssd under 50k",
        "good gaming laptoop with graphics under 30k",
        "asdfghjkl",
        "something good",
        "what should i buy",
        "earbuds",
    ]

    for q in test_queries:
        res = understand(q)
        print("\n" + "=" * 60)
        print(f"QUERY: {q}")
        print("=" * 60)
        print(res.explain())
