"""
product_constraints.py — Shared product-type, material, accessory, and budget rules.

This is the source of truth for:
  - product type vs material (denim is fabric, jacket is the product)
  - accessory vs primary product
  - realistic vs unrealistic budgets
  - category evidence used by search validation and ranking
  - query-completion vocabularies
"""
from __future__ import annotations

import re
from typing import Any


# ── Materials (never treated as a product category) ───────────────────────────
MATERIALS: tuple[str, ...] = (
    'cotton blend', 'poly cotton', 'faux leather', 'pu leather',
    'leather', 'cotton', 'polyester', 'nylon', 'wool', 'silk', 'rubber',
    'plastic', 'metal', 'wood', 'glass', 'denim', 'velvet', 'suede',
    'canvas', 'linen', 'rayon', 'viscose', 'jute', 'fleece', 'mesh',
    'chiffon', 'georgette', 'khadi', 'satin', 'lycra', 'spandex',
)

# ── Styles / patterns ─────────────────────────────────────────────────────────
STYLES: tuple[str, ...] = (
    'checkered', 'checked', 'plaid', 'striped', 'printed', 'solid',
    'floral', 'graphic', 'plain', 'embroidered', 'tie-dye', 'abstract',
    'geometric', 'polka dot', 'formal', 'casual', 'party', 'slim fit',
    'regular fit', 'oversized', 'skinny', 'relaxed',
)

COLORS: tuple[str, ...] = (
    'navy blue', 'sky blue', 'off white', 'dark green', 'light blue',
    'black', 'white', 'red', 'blue', 'green', 'pink', 'yellow', 'purple',
    'orange', 'grey', 'gray', 'silver', 'gold', 'brown', 'navy', 'beige',
    'maroon', 'cream', 'olive', 'teal', 'coral', 'khaki',
)

# Typical Indian retail floors (INR) for a real primary product in that category.
# Used to tell "cheap but possible" from "impossible for this product type".
PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    'laptop': {
        'aliases': ('laptop', 'laptops', 'notebook', 'notebooks', 'ultrabook',
                    'chromebook', 'macbook', 'macbooks'),
        'dept': 'Laptops', 'amazon_cat': 'Electronics',
        'typical_min': 18000, 'typical_max': 250000,
        'pos': ('laptop', 'notebook', 'ultrabook', 'chromebook', 'macbook',
                'ideapad', 'thinkpad', 'vivobook', 'zenbook', 'pavilion',
                'victus', 'tuf gaming', 'predator', 'legion', 'inspiron', 'vostro'),
        'neg': ('desktop', 'toy laptop', 'laptop bag', 'laptop sleeve',
                'laptop skin', 'laptop sticker', 'laptop cover', 'laptop stand',
                'cooling pad', 'mouse pad', 'keyboard skin', 'adapter', 'charger',
                'battery', 'batteries', 'replacement battery', 'battery pack',
                'laptop battery', 'power bank', 'internal battery', 'cell', 'cells',
                'screen replacement', 'replacement screen', 'keyboard replacement',
                'display panel', 'power adapter'),
    },
    'phone': {
        'aliases': ('phone', 'phones', 'mobile', 'mobiles', 'smartphone',
                    'smartphones', 'iphone', 'iphones'),
        'dept': 'Mobile Phones', 'amazon_cat': 'Cell_Phones_and_Accessories',
        'typical_min': 4000, 'typical_max': 180000,
        'pos': ('phone', 'smartphone', 'mobile', 'iphone', 'galaxy', '5g phone'),
        'neg': ('phone case', 'back cover', 'tempered glass', 'screen protector',
                'phone cover', 'phone skin', 'dummy phone', 'toy phone',
                'pop socket', 'phone holder', 'phone stand'),
    },
    'headphones': {
        'aliases': ('headphone', 'headphones', 'headset', 'headsets'),
        'dept': 'Headphones', 'amazon_cat': 'Electronics',
        'typical_min': 499, 'typical_max': 40000,
        'pos': ('headphone', 'over-ear', 'on-ear', 'headset', 'over ear', 'on ear'),
        'neg': ('earbuds', 'neckband', 'tws', 'earphone', 'speaker', 'ear tip'),
    },
    'earbuds': {
        'aliases': ('earbud', 'earbuds', 'airpods', 'airdopes', 'tws'),
        'dept': 'Earbuds', 'amazon_cat': 'Electronics',
        'typical_min': 499, 'typical_max': 25000,
        'pos': ('earbuds', 'tws', 'true wireless', 'airdopes', 'airpods', 'buds'),
        'neg': ('headphone', 'neckband', 'speaker', 'wired earphone', 'earphone'),
    },
    'earphones': {
        'aliases': ('earphone', 'earphones'),
        'dept': 'Earphones', 'amazon_cat': 'Electronics',
        'typical_min': 149, 'typical_max': 8000,
        'pos': ('earphone', 'wired earphone', 'in-ear', 'iem'),
        'neg': ('headphone', 'neckband', 'earbuds', 'tws', 'speaker'),
    },
    'jacket': {
        'aliases': ('jacket', 'jackets', 'coat', 'coats', 'blazer', 'blazers',
                    'windbreaker', 'windcheater', 'bomber'),
        'dept': 'Jackets', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 699, 'typical_max': 15000,
        'pos': ('jacket', 'coat', 'blazer', 'windbreaker', 'windcheater',
                'bomber jacket', 'denim jacket', 'leather jacket', 'varsity'),
        'neg': ('jeans', 'jean', 'trousers', 'pants', 'shirt', 't-shirt',
                'hoodie', 'sweater', 'shorts'),
    },
    'hoodie': {
        'aliases': ('hoodie', 'hoodies', 'sweatshirt', 'sweatshirts',
                    'sweater', 'sweaters', 'pullover', 'pullovers', 'cardigan'),
        'dept': 'Sweatshirts', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 399, 'typical_max': 8000,
        'pos': ('hoodie', 'sweatshirt', 'sweater', 'pullover', 'cardigan'),
        'neg': ('jacket', 'jeans', 'shirt', 't-shirt'),
    },
    'shirt': {
        'aliases': ('shirt', 'shirts'),
        'dept': 'Shirts', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 299, 'typical_max': 8000,
        'pos': ('formal shirt', 'casual shirt', 'cotton shirt', 'linen shirt',
                'oxford shirt', 'check shirt', 'checked shirt', 'full sleeve shirt',
                'shirt'),
        'neg': ('t-shirt', 'tshirt', 't shirt', 'jeans', 'jacket', 'hoodie',
                'track pant'),
        'alias_exclude': ('t-shirt', 'tshirt', 't shirt', 'sweatshirt'),
    },
    't-shirt': {
        'aliases': ('t-shirt', 't-shirts', 'tshirt', 'tshirts', 'tee', 'tees',
                    'polo shirt', 'polo t-shirt'),
        'dept': 'T-Shirts', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 199, 'typical_max': 4000,
        'pos': ('t-shirt', 'tshirt', 't shirt', 'tee', 'polo t-shirt',
                'round neck', 'crew neck'),
        'neg': ('formal shirt', 'jeans', 'jacket', 'trouser'),
    },
    'jeans': {
        'aliases': ('jean', 'jeans', 'denims'),
        'dept': 'Jeans', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 499, 'typical_max': 8000,
        'pos': ('jeans', 'denim jeans', 'skinny jeans', 'slim fit jeans'),
        'neg': ('jacket', 'shirt', 't-shirt', 'shorts', 'trouser', 'denim jacket'),
    },
    'trouser': {
        'aliases': ('trouser', 'trousers', 'pants', 'chinos', 'cargos'),
        'dept': 'Trousers', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 399, 'typical_max': 6000,
        'pos': ('trouser', 'trousers', 'pants', 'chinos', 'formal pant'),
        'neg': ('jeans', 'shorts', 'jacket', 'shirt'),
    },
    'office wear': {
        'aliases': ('office wear', 'formal wear', 'work wear', 'workwear', 'business wear'),
        'dept': 'Office Wear', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 499, 'typical_max': 15000,
        'pos': ('office wear', 'formal shirt', 'formal wear', 'formal trouser', 'work wear', 'formal pant', 'blazer', 'office shirt', 'formal dress'),
        'neg': ('t-shirt', 'shorts', 'track pant', 'nightwear', 'pajama', 'gym wear'),
    },
    'shoes': {
        'aliases': ('shoe', 'shoes', 'sneaker', 'sneakers', 'footwear',
                    'loafers', 'boots'),
        'dept': 'Footwear', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 399, 'typical_max': 20000,
        'pos': ('shoes', 'sneakers', 'footwear', 'running shoes', 'loafers',
                'boots', 'formal shoes', 'casual shoes'),
        'neg': ('socks', 'shoe polish', 'shoe rack', 'laces only', 'insole',
                't-shirt', 'shirt'),
    },
    'watch': {
        'aliases': ('watch', 'watches', 'wristwatch', 'wrist watch'),
        'dept': 'Watches', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 399, 'typical_max': 80000,
        'pos': ('watch', 'wrist watch', 'analog watch', 'digital watch'),
        'neg': ('wall clock', 'strap only', 'watch strap'),
    },
    'smartwatch': {
        'aliases': ('smartwatch', 'smartwatches', 'smart watch', 'fitness band'),
        'dept': 'Smartwatches', 'amazon_cat': 'Electronics',
        'typical_min': 799, 'typical_max': 50000,
        'pos': ('smartwatch', 'smart watch', 'fitness band', 'smart band'),
        'neg': ('wall clock', 'watch strap only'),
    },
    'bag': {
        'aliases': ('bag', 'bags', 'backpack', 'backpacks', 'handbag', 'handbags'),
        'dept': 'Bags', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 299, 'typical_max': 15000,
        'pos': ('bag', 'backpack', 'handbag', 'rucksack'),
        'neg': ('shoe', 'shirt'),
    },
    'kurta': {
        'aliases': ('kurta', 'kurtas', 'kurti', 'kurtis'),
        'dept': 'Ethnic Wear', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 399, 'typical_max': 8000,
        'pos': ('kurta', 'kurti'),
        'neg': ('saree', 'jeans', 'shirt'),
    },
    'dress': {
        'aliases': ('dress', 'dresses', 'frock', 'gown', 'gowns'),
        'dept': 'Dresses', 'amazon_cat': 'Clothing_Shoes_and_Jewelry',
        'typical_min': 499, 'typical_max': 12000,
        'pos': ('dress', 'gown', 'frock'),
        'neg': ('shirt', 'jeans'),
    },
    'television': {
        'aliases': ('television', 'televisions', 'tv', 'tvs', 'smart tv', 'led tv'),
        'dept': 'Televisions', 'amazon_cat': 'Electronics',
        'typical_min': 8000, 'typical_max': 400000,
        'pos': ('television', 'smart tv', 'led tv', 'oled', 'qled'),
        'neg': ('tv stand', 'tv cover', 'tv unit', 'remote only'),
    },
    'tablet': {
        'aliases': ('tablet', 'tablets', 'ipad', 'ipads'),
        'dept': 'Tablets', 'amazon_cat': 'Electronics',
        'typical_min': 7000, 'typical_max': 150000,
        'pos': ('tablet', 'ipad'),
        'neg': ('tablet cover', 'tablet case', 'stylus only'),
    },
    'camera': {
        'aliases': ('camera', 'cameras', 'dslr', 'mirrorless'),
        'dept': 'Cameras', 'amazon_cat': 'Electronics',
        'typical_min': 15000, 'typical_max': 400000,
        'pos': ('camera', 'dslr', 'mirrorless'),
        'neg': ('camera bag', 'lens cap', 'tripod only'),
    },
}

# Accessories for a requested primary category — never substitute these.
_ACCESSORY_CORE = (
    r'case', r'cover', r'skin', r'skins', r'sticker', r'decal', r'wrap',
    r'sleeve', r'pouch', r'protector', r'tempered\s*glass', r'screen\s*guard',
    r'screen\s*protector', r'stand', r'holder', r'mount', r'charger', r'cable',
    r'adapter', r'bag', r'backpack', r'strap', r'band\s*only',
    r'battery', r'batteries', r'battery\s*pack', r'replacement\s*battery',
    r'spare\s*battery', r'internal\s*battery', r'power\s*bank', r'power\s*adapter',
    r'cell(?:s)?', r'replacement\s*(?:part|parts|screen|keyboard|display)',
)

ACCESSORY_RE = re.compile(
    r'\b(?:' + '|'.join(_ACCESSORY_CORE) + r')\b',
    re.I,
)

_PRIMARY_CATEGORY_ACCESSORIES: dict[str, tuple[str, ...]] = {
    'laptop': (
        'laptop bag', 'laptop sleeve', 'laptop skin', 'laptop cover',
        'laptop sticker', 'laptop stand', 'cooling pad', 'laptop backpack',
        'laptop battery', 'replacement battery', 'battery pack', 'internal battery',
        'laptop charger', 'power adapter', 'replacement keyboard', 'replacement screen',
        'lcd panel', 'display replacement', 'cooling fan',
    ),
    'phone': (
        'phone case', 'phone cover', 'back cover', 'screen protector',
        'tempered glass', 'phone skin', 'pop socket', 'phone battery',
        'replacement battery', 'charging cable', 'charger adapter',
    ),
    'jacket': ('jacket cover',),
    'headphones': ('ear cushion', 'ear pad', 'headband only'),
}

# Brands commonly used for next-word completion (India-focused)
COMPLETION_BRANDS: dict[str, tuple[str, ...]] = {
    'laptop': ('HP', 'Dell', 'Lenovo', 'ASUS', 'Acer', 'MSI', 'Apple'),
    'phone': ('Samsung', 'Redmi', 'Realme', 'Vivo', 'OnePlus', 'iPhone', 'Motorola'),
    'headphones': ('Sony', 'JBL', 'boAt', 'Bose', 'Sennheiser'),
    'earbuds': ('boAt', 'Noise', 'OnePlus', 'JBL', 'Apple'),
    'shoes': ('Nike', 'Adidas', 'Puma', 'Campus', 'Skechers', 'Red Tape'),
    'shirt': ('Peter England', 'Allen Solly', 'Van Heusen', 'Louis Philippe'),
    'jacket': ('Levi\'s', 'Wrangler', 'Roadster', 'HRX', 'Puma'),
    'jeans': ('Levi\'s', 'Wrangler', 'Lee', 'Pepe Jeans'),
    'default': ('Nike', 'Adidas', 'Samsung', 'HP', 'boAt', 'Puma', 'ASUS', 'Acer'),
}

PRODUCT_NOUNS_FOR_COMPLETION: tuple[str, ...] = (
    'shirt', 'shirts', 't-shirt', 'jacket', 'jackets', 'jeans', 'shoes',
    'sneakers', 'laptop', 'laptops', 'phone', 'phones', 'headphones',
    'earbuds', 'earphones', 'hoodie', 'sweater', 'watch', 'bag', 'kurta',
    'dress', 'trousers', 'blazer', 'coat',
)


def _word_pat(alias: str) -> re.Pattern:
    return re.compile(r'\b' + re.escape(alias) + r'(?:es|s)?\b', re.I)


def detect_materials(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for mat in sorted(MATERIALS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(mat) + r'\b', lower) and mat not in found:
            found.append(mat)
    return found


def detect_styles(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for st in sorted(STYLES, key=len, reverse=True):
        if re.search(r'\b' + re.escape(st) + r'\b', lower) and st not in found:
            found.append(st)
    return found


def _alias_matches(text: str, cat: str, aliases: tuple[str, ...]) -> list[tuple[int, str]]:
    """Return (start_index, alias) hits, skipping excluded phrases (e.g. t-shirt for shirt)."""
    hits = []
    excludes = PRODUCT_CATALOG.get(cat, {}).get('alias_exclude') or ()
    lower = text.lower()
    for excl in excludes:
        lower = re.sub(r'\b' + re.escape(excl) + r'\b', ' ' * len(excl), lower)
    for alias in aliases:
        for m in re.finditer(r'\b' + re.escape(alias) + r'\b', lower, re.I):
            hits.append((m.start(), alias))
    return hits


def detect_product_type(text: str) -> str | None:
    """
    Head-noun product type. Material never wins.
    Handles feature clauses (e.g. 'with a good camera', 'with 16GB RAM')
    so that attributes inside prepositional phrases do not hijack the primary product.

    'phone with a good camera' → phone
    'phone under 30k with good camera and long battery life' → phone
    'denim jacket' → jacket
    'cotton shirt' → shirt
    'laptop bag' → bag
    """
    if not text:
        return None

    # Handle 'camera phone' explicitly -> phone
    if re.search(r'\bcamera\s*phones?\b', text, re.I):
        return 'phone'

    # If query has a feature modifier clause ("with ...", "having ...", "featuring ..."),
    # check if a primary product exists BEFORE the preposition
    preposition_match = re.search(r'\b(?:with|having|featuring|equipped\s+with|built[\s-]in)\b', text, re.I)
    if preposition_match:
        main_part = text[:preposition_match.start()].strip()
        main_best = _detect_head_noun_in_phrase(main_part)
        if main_best:
            return main_best

    # If both phone and camera appear, phone is the primary product unless camera is DSLR/vlogging/action
    has_phone = bool(re.search(r'\b(?:phones?|mobiles?|smartphones?|iphones?|android)\b', text, re.I))
    has_camera = bool(re.search(r'\b(?:cameras?|dslrs?|mirrorless|camra|gopros?)\b', text, re.I))
    if has_phone and has_camera:
        # Check if it's explicitly a dedicated camera query or phone vs camera comparison
        if not re.search(r'\b(?:dslr|mirrorless|action\s*camera|gopro|vlog|vs|versus|compare)\b', text, re.I):
            return 'phone'

    # If both laptop and bag/backpack appear:
    # "laptop bag", "laptop backpack", "backpack for laptop" -> bag
    has_laptop = bool(re.search(r'\b(?:laptops?|notebooks?|ultrabooks?|macbooks?)\b', text, re.I))
    has_bag = bool(re.search(r'\b(?:bags?|backpacks?|rucksacks?)\b', text, re.I))
    if has_laptop and has_bag:
        if re.search(r'\b(?:laptop\s+(?:bag|backpack)|backpack\s+for\s+laptop|bag\s+for\s+laptop)\b', text, re.I):
            return 'bag'

    return _detect_head_noun_in_phrase(text)


def _detect_head_noun_in_phrase(phrase: str) -> str | None:
    if not phrase:
        return None
    best: tuple[int, int, str] | None = None  # (start, alias_len, cat)
    for cat, meta in PRODUCT_CATALOG.items():
        for start, alias in _alias_matches(phrase, cat, meta['aliases']):
            # Prefer the last product noun (head of the phrase)
            cand = (start, len(alias), cat)
            if best is None:
                best = cand
            else:
                if start > best[0] or (start == best[0] and len(alias) > best[1]):
                    best = cand
    return best[2] if best else None


def catalog_rules(category: str | None) -> dict[str, Any] | None:
    if not category:
        return None
    key = category.lower().strip()
    if key in PRODUCT_CATALOG:
        return PRODUCT_CATALOG[key]
    aliases = {
        'laptops': 'laptop', 'mobile phones': 'phone', 'mobile': 'phone',
        'jackets': 'jacket', 'shirts': 'shirt', 't-shirts': 't-shirt',
        'footwear': 'shoes', 'sneakers': 'shoes', 'headphones': 'headphones',
        'sweatshirts': 'hoodie', 'sweater': 'hoodie', 'trousers': 'trouser',
        'pants': 'trouser', 'formal wear': 'shirt',
    }
    mapped = aliases.get(key)
    return PRODUCT_CATALOG.get(mapped) if mapped else None


def typical_price_band(category: str | None) -> tuple[int | None, int | None]:
    rules = catalog_rules(category)
    if not rules:
        return None, None
    return int(rules['typical_min']), int(rules['typical_max'])


def analyze_budget(category: str | None, max_price: int | None) -> dict[str, Any]:
    """
    A) ok — low but realistic
    B) unrealistic — far below typical primary-product prices
    C) tight — possible but often slightly above
    """
    out = {
        'status': 'none',
        'typical_min': None,
        'typical_max': None,
        'max_price': max_price,
        'category': category,
    }
    if max_price is None:
        return out
    lo, hi = typical_price_band(category)
    out['typical_min'] = lo
    out['typical_max'] = hi
    if lo is None:
        out['status'] = 'ok'
        return out
    if max_price < lo * 0.25 or max_price < lo * 0.4 and max_price < 1000 and lo >= 4000:
        out['status'] = 'unrealistic'
    elif max_price < lo:
        out['status'] = 'tight'
    else:
        out['status'] = 'ok'
    return out


def is_accessory_title(title: str, requested_category: str | None = None) -> bool:
    t = (title or '').lower()
    if not t:
        return False
    cat = (requested_category or '').lower()

    # For bag / backpack requests: a backpack or bag (even laptop backpack) is the PRIMARY product!
    if cat in ('bag', 'bags', 'backpack', 'backpacks', 'handbag', 'handbags'):
        if re.search(r'\b(?:rain\s*cover(?:\s*only)?|bag\s*strap|backpack\s*strap|shoulder\s*strap(?:\s*only)?|luggage\s*tag|zipper\s*pull|bag\s*lock)\b', t, re.I):
            return True
        return False

    extra = _PRIMARY_CATEGORY_ACCESSORIES.get(cat, ())
    for phrase in extra:
        if phrase in t:
            return True

    # Strict check for laptops: replacement batteries, power adapters, replacement parts are NEVER laptops
    if cat in ('laptop', 'laptops', 'notebook', 'notebooks', 'ultrabook', 'macbook'):
        if re.search(
            r'\b(?:(?:replacement|internal|compatible|spare|backup|laptop|notebook|li-ion)\s+batter(?:y|ies)|'
            r'batter(?:y|ies)\s+for|battery\s+pack|charger\s+for|adapter\s+for|keyboard\s+for|'
            r'power\s+adapter\s+for|display\s+for|screen\s+for|replacement\s+(?:screen|keyboard|display|panel|battery|motherboard)|'
            r'cooling\s+fan\s+for|ram\s+stick\s+for)\b',
            t, re.I,
        ):
            return True
        # If "battery" is in the title, and it does not have clear laptop indicators like "laptop with", "laptop computer"
        if re.search(r'\bbatter(?:y|ies)\b', t, re.I):
            # Check if this listing is a battery component (mAh, Wh, cell, pin, replacement, compatible)
            if re.search(r'\b(?:mah\b|whr?\b|cells?\b|voltage|pin\b|replacement|compatible|laptop\s+battery)\b', t, re.I):
                return True
            # If title starts with brand + battery (e.g. "Dell Battery", "HP Laptop Battery")
            if re.search(r'\b(?:dell|hp|lenovo|asus|acer|apple|macbook)\s+(?:laptop\s+)?batter(?:y|ies)\b', t, re.I):
                return True

    # Strict check for phones: keypad feature phones, car phones, toy phones are NOT smartphones
    if cat in ('phone', 'phones', 'mobile', 'mobiles', 'smartphone', 'smartphones'):
        if re.search(
            r'\b(?:keypad\s*(?:mobile|phone)|multimedia\s*keypad|car\s*phone|toy\s*phone|dummy\s*phone|feature\s*phone|basic\s*(?:mobile|phone)|senior\s*citizen\s*phone|i\s*kall\s*k\d+)\b',
            t, re.I,
        ):
            return True

    # "laptop bag / phone case" style: category noun + accessory noun
    if cat and ACCESSORY_RE.search(t):
        cat_rules = catalog_rules(cat)
        aliases = cat_rules['aliases'] if cat_rules else (cat,)
        if any(re.search(r'\b' + re.escape(a) + r'\b', t) for a in aliases):
            # Primary products can mention "with charger" — require accessory as the item
            if re.search(
                r'\b(?:for\s+(?:laptop|phone|mobile|iphone|macbook)|'
                r'(?:laptop|phone|mobile)\s+(?:bag|case|cover|skin|stand|sleeve|sticker|battery|batteries|charger|adapter)|'
                r'(?:case|cover|skin|stand|sleeve|protector|tempered|battery|batteries|charger|adapter)\b)',
                t, re.I,
            ):
                return True
    if ACCESSORY_RE.search(t) and re.search(
        r'\b(?:case|cover|skin|sticker|decal|sleeve|pouch|protector|'
        r'tempered\s*glass|stand|holder|mount|battery|batteries|charger|adapter)\b', t, re.I,
    ):
        # Don't flag a "phone" whose title is the actual phone
        if re.search(
            r'\b(?:back\s*cover|phone\s*case|laptop\s*skin|laptop\s*bag|'
            r'screen\s*protector|tempered\s*glass|laptop\s*stand|cooling\s*pad|'
            r'replacement\s*battery|laptop\s*battery|phone\s*battery)\b',
            t, re.I,
        ):
            return True
    return False


def title_matches_category(title: str, category: str | None) -> bool:
    rules = catalog_rules(category)
    if not rules:
        return True
    t = (title or '').lower()
    for excl in rules['neg']:
        if re.search(r'\b' + re.escape(excl) + r'(?:es|s)?\b', t):
            # Allow "denim jacket" when category is jacket even if 'jeans' is nearby
            if category == 'jacket' and excl in ('jeans', 'jean') and re.search(r'\bjacket', t):
                continue
            if category == 'shirt' and excl in ('t-shirt', 'tshirt', 't shirt'):
                return False
            if category != 'jeans':
                return False
            if excl in ('jacket', 'denim jacket'):
                return False
    has_pos = any(re.search(r'\b' + re.escape(p) + r'(?:es|s)?\b', t) for p in rules['pos'])
    if category == 'jeans':
        # denim alone is not enough — must be jeans/pants, not a jacket
        if re.search(r'\b(?:jacket|shirt|t-shirt)\b', t):
            return False
        has_pos = bool(re.search(r'\bjeans?\b', t))
    return has_pos


def title_matches_material(title: str, materials: list[str] | None) -> str:
    """match | mismatch | unknown"""
    if not materials:
        return 'match'
    t = (title or '').lower()
    for mat in materials:
        m = mat.lower()
        if m == 'denim' and re.search(r'\b(?:denim|jean)\b', t):
            return 'match'
        if re.search(r'\b' + re.escape(m) + r'\b', t):
            return 'match'
    # Conflicting garment type with a different material mentioned is mismatch only
    # if another known material is clearly stated.
    other = [x for x in MATERIALS if x not in {m.lower() for m in materials}]
    if any(re.search(r'\b' + re.escape(o) + r'\b', t) for o in other):
        return 'mismatch'
    return 'unknown'


def dept_for_category(category: str | None) -> tuple[str | None, str | None]:
    rules = catalog_rules(category)
    if not rules:
        return None, None
    return rules.get('dept'), rules.get('amazon_cat')


def generic_category_rules_dict() -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for cat, meta in PRODUCT_CATALOG.items():
        out[cat] = {
            'pos': list(meta['pos']),
            'neg': list(meta['neg']),
        }
    return out


def format_unrealistic_budget_message(category: str, max_price: int, cheapest: float | None) -> str:
    label = category
    band_lo, band_hi = typical_price_band(category)
    range_s = ''
    if band_lo and band_hi:
        range_s = f" Typical {label} prices in India start around ₹{band_lo:,}."
    if cheapest and cheapest > 0:
        diff = int(cheapest - max_price)
        extra = f" The cheapest matching {label} I found is ₹{cheapest:,.0f}"
        if diff > 0:
            extra += f", so you would need to increase your budget by ₹{diff:,}."
        else:
            extra += "."
        return (
            f"No {label} matching your ₹{max_price:,} budget was found. "
            f"The budget is far below the typical price of an actual {label}.{range_s}"
            f"{extra} I can keep this cheapest {label}, or you can increase your budget."
        )
    return (
        f"No {label} matching your ₹{max_price:,} budget was found. "
        f"The budget is far below the typical price of an actual {label}.{range_s} "
        f"I can either search for the cheapest {label} available or you can increase your budget."
    )


def format_near_budget_message(category: str, max_price: int, cheapest: float) -> str:
    diff = int(cheapest - max_price)
    if diff <= 0:
        return ''
    return (
        f"No exact match was found under ₹{max_price:,}. "
        f"The cheapest matching {category} I found is ₹{cheapest:,.0f}, "
        f"so you would need to increase your budget by ₹{diff:,}."
    )


_STOP = {
    'a', 'an', 'the', 'of', 'for', 'to', 'me', 'my', 'please', 'pls',
    'under', 'below', 'with', 'and', 'or', 'in',
}


def complete_shopping_query(raw: str, limit: int = 4) -> list[str]:
    """
    Query completion (not grammar rewrite). Preserves the typed prefix.
    """
    raw = (raw or '').strip()
    if len(raw) < 2:
        return []

    # Keep original casing/spacing of the stem; only complete the tail.
    m_trail = re.match(r'^(.*?)(\S+)$', raw)
    if not m_trail:
        return []
    stem, last = m_trail.group(1), m_trail.group(2)
    last_l = last.lower()
    full_l = raw.lower()

    product = detect_product_type(full_l)
    materials = detect_materials(full_l)
    styles = detect_styles(full_l)
    has_budget = bool(re.search(r'\b(?:under|below|upto?|within)\b|\d', full_l))

    suggestions: list[str] = []

    def add(text: str):
        text = re.sub(r'\s+', ' ', text).strip()
        if text and text.lower() != full_l and text not in suggestions:
            suggestions.append(text)

    def join(prefix: str, word: str) -> str:
        if prefix.endswith(' ') or prefix == '':
            return prefix + word
        return prefix + word if not prefix else prefix + word

    # Incomplete last token → complete that word from vocab
    vocab_next: list[str] = []
    vocab_next.extend(PRODUCT_NOUNS_FOR_COMPLETION)
    vocab_next.extend(MATERIALS)
    vocab_next.extend(STYLES)
    vocab_next.extend(COLORS)
    for brands in COMPLETION_BRANDS.values():
        vocab_next.extend(brands)
    vocab_next.extend(('men', 'women', 'kids', 'Asus', 'Acer', 'HP', 'Dell'))

    last_is_article = last_l in ('a', 'an', 'of', 'the')
    last_complete_known = last_l in {v.lower() for v in vocab_next} or last_l in _STOP

    if not last_is_article and not last_complete_known:
        matches = [v for v in vocab_next if v.lower().startswith(last_l) and v.lower() != last_l]
        # Prefer products if a style/material/color is already present
        if styles or materials or re.search(r'\b(?:black|white|blue|red)\b', full_l):
            prod_first = [v for v in matches if v.lower() in PRODUCT_NOUNS_FOR_COMPLETION]
            matches = prod_first + [v for v in matches if v not in prod_first]
        for v in matches[:6]:
            add(stem + v)

    # Next-slot completions from a complete (or article) prefix
    prefix_keep = raw if (last_is_article or last_complete_known) else stem.rstrip()
    if last_is_article:
        prefix_keep = raw.rstrip() + ' '

    def with_next(words: list[str]):
        base = prefix_keep if prefix_keep.endswith(' ') else prefix_keep + ' '
        for w in words:
            add(base + w)

    if product:
        brands = list(COMPLETION_BRANDS.get(product, COMPLETION_BRANDS['default']))
        if last_is_article or last_l in ('of', 'by', 'from'):
            with_next(brands[:4])
        elif not re.search(r"\b(?:men'?s?|women'?s?|kids?)\b", full_l):
            add(f"{raw} for men")
            add(f"{raw} for women")
        if not has_budget:
            add(f"{raw} under ₹1,000" if typical_price_band(product)[0] and typical_price_band(product)[0] < 2000
                else f"{raw} under ₹{typical_price_band(product)[0]:,}")
        if materials:
            add(f"{raw} {materials[0]}" if materials[0] not in full_l else raw)
    else:
        # No product yet — complete with likely product nouns
        if styles or last_l in STYLES or any(s in full_l for s in ('checkered', 'checked', 'striped', 'printed')):
            with_next(['shirt', 'jacket', 'shirt for men', 'shirt under ₹1,000'])
        elif materials:
            mat = materials[0]
            if mat == 'denim':
                with_next(['jacket', 'jacket for men', 'shirt', 'jeans'])
            elif mat in ('cotton', 'linen'):
                with_next(['shirt', 'shirt for men', 'kurta', 't-shirt'])
            elif mat == 'leather':
                with_next(['jacket', 'shoes', 'bag'])
            else:
                with_next(['shirt', 'jacket', 'shoes'])
        elif re.search(r'\b(?:black|white|blue|red|green)\b', full_l) or (
            not last_complete_known and any(c.startswith(last_l) for c in COLORS)
        ):
            with_next(['shirt', 'shoes', 'jacket', 't-shirt'])
        elif last_is_article:
            with_next(['laptop', 'phone', 'shirt', 'denim jacket'])
        else:
            with_next(['shirt', 'jacket', 'laptop', 'shoes'])

    # If user already typed a product, do not drift to unrelated products
    if product:
        filtered = []
        for s in suggestions:
            other = detect_product_type(s)
            if other is None or other == product:
                filtered.append(s)
        if filtered:
            suggestions = filtered

    # Dedup while preserving order
    seen = set()
    out = []
    for s in suggestions:
        k = s.lower().strip()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= limit:
            break
    return out
