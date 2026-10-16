"""
product_deduplicator.py – Comprehensive Product Deduplication Engine
────────────────────────────────────────────────────────────────────
Guarantees that search results, alternatives, and recommendations never
contain the same product multiple times, duplicate model variations
(e.g., shoe sizes, store variants), or identical listings from multiple sellers.
"""
from __future__ import annotations
import re
from typing import Any

# Common filler words in product listings
_STOP_WORDS = {
    'with', 'for', 'and', 'the', 'in', 'of', 'at', 'by', 'on', 'a', 'an', 'to',
    'men', 'mens', "men's", 'women', 'womens', "women's", 'unisex', 'adult',
    'pack', 'combo', 'color', 'colour', 'set', 'piece', 'pcs',
    'black', 'white', 'blue', 'red', 'green', 'yellow', 'grey', 'gray', 'pink',
    'online', 'india', 'buy', 'best', 'latest', 'new', 'original', 'genuine',
}

# Key model series keywords that distinguish different models within a brand
_DISTINCT_MODEL_KEYWORDS = {
    'victus', 'pavilion', 'inspiron', 'vostro', 'ideapad', 'thinkpad', 'zenbook',
    'vivobook', 'legion', 'predator', 'aspire', 'galaxy', 'nord', 'redmi', 'poco',
    'thunder', 'airdopes', 'rockerz', 'hurricane', 'duramo', 'pegasus', 'downshifter',
    'revolution', 'wave', 'storm', 'immortal', 'ignite', 'flyer', 'airmax', 'zoom',
    'steens', 'thermoball', 'contend', 'speed',
}


def clean_link_for_dedupe(link: str | None) -> str:
    """Normalize a product URL by removing tracking query parameters."""
    if not link or not isinstance(link, str):
        return ""
    l = link.strip().lower().split('#')[0]
    if 'google.' in l:
        l = re.sub(r'(&|\?)utm_[^&]+', '', l)
        l = re.sub(r'(&|\?)ved=[^&]+', '', l)
        return l
    # For merchant product pages (Amazon, Flipkart), strip query params
    l = re.sub(r'[\?\#].*$', '', l)
    return l


def get_title_tokens(title: str | None) -> set[str]:
    """Extract clean, meaningful token set from product title."""
    if not title or not isinstance(title, str):
        return set()
    t = title.lower()
    # Remove parenthetical / bracketed content like (Off-White, 8), [Black, Size 9], (Pack of 2)
    t = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', ' ', t)
    # Remove version punctuation like 5.3 -> 5
    t = re.sub(r'(\d+)\.\d+', r'\1', t)
    # Remove size markers e.g. "Size 8", "UK 7", "42 EU"
    t = re.sub(r'\b(?:size|uk|us|eu)\s*[:\-]?\s*\d+(?:\.\d+)?\b', ' ', t)
    # Remove non-alphanumeric characters
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    tokens = {w for w in t.split() if len(w) > 1 and w not in _STOP_WORDS}
    return tokens


def get_canonical_title_key(title: str | None, brand: str = "") -> str:
    """
    Produce a canonical signature for product title by stripping noise,
    sizes, and formatting variations.
    """
    if not title or not isinstance(title, str):
        return ""
    t = title.lower()
    t = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', ' ', t)
    t = re.sub(r'(\d+)\.\d+', r'\1', t)
    t = re.sub(r'\b(?:size|uk|us|eu)\s*[:\-]?\s*\d+(?:\.\d+)?\b', ' ', t)
    t = re.sub(r'\b(?:online|india|free\s+shipping|lowest\s*rate|best\s*price)\b', ' ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    words = [w for w in t.split() if len(w) > 1 and w not in _STOP_WORDS]
    # First 6 significant words form a strong canonical signature
    return ' '.join(words[:6])


def is_duplicate_product(p1: dict[str, Any], p2: dict[str, Any]) -> bool:
    """
    Determines whether p1 and p2 represent the exact same product,
    a repeat seller listing, or a minor variant (e.g. shoe size) of the same model.
    """
    if p1 is p2:
        return True

    # 1. Direct link check (if base URLs are identical)
    l1 = clean_link_for_dedupe(p1.get('link') or p1.get('product_link'))
    l2 = clean_link_for_dedupe(p2.get('link') or p2.get('product_link'))
    if l1 and l2 and l1 == l2:
        return True

    # 2. Exact Title Check
    t1 = str(p1.get('title') or '').strip()
    t2 = str(p2.get('title') or '').strip()
    if not t1 or not t2:
        return False
    if t1.lower() == t2.lower():
        return True

    # 3. Canonical Key Check
    b1 = str(p1.get('brand') or '').strip().lower()
    b2 = str(p2.get('brand') or '').strip().lower()
    ck1 = get_canonical_title_key(t1, b1)
    ck2 = get_canonical_title_key(t2, b2)
    if ck1 and ck2 and ck1 == ck2:
        return True

    # 4. Token Overlap & Model Identifier Comparison
    tok1 = get_title_tokens(t1)
    tok2 = get_title_tokens(t2)
    if not tok1 or not tok2:
        return False

    # Extract distinct model names/numbers (e.g. '15s', 'm34', 'victus', 'thunder')
    def extract_model_identifiers(tokens: set[str]) -> set[str]:
        return {
            w for w in tokens
            if (any(c.isdigit() for c in w) and len(w) >= 2) or w in _DISTINCT_MODEL_KEYWORDS
        }

    models1 = extract_model_identifiers(tok1)
    models2 = extract_model_identifiers(tok2)

    # If both have explicit, distinct model keywords and they don't overlap, they are DIFFERENT models
    if models1 and models2 and not (models1 & models2):
        return False

    overlap = tok1 & tok2
    min_len = min(len(tok1), len(tok2))
    if min_len < 3:
        return False

    ratio_min = len(overlap) / float(min_len)
    jaccard = len(overlap) / float(len(tok1 | tok2))

    # Same brand and high token overlap (e.g. "Zebronics Thunder..." vs "Zebronics Thunder Bluetooth...")
    if b1 and b2 and b1 == b2:
        if ratio_min >= 0.75:
            return True

    # Regardless of brand field (sometimes brand is empty or unparsed):
    # If one title contains almost all tokens of the other (>= 85% subset)
    if ratio_min >= 0.85:
        return True

    if jaccard >= 0.70:
        return True

    return False


def deduplicate_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Returns a deduplicated list of products, preserving the original ranking order.
    Eliminates identical titles, same-model variants, and repeat listings from multiple stores.
    """
    unique_products: list[dict[str, Any]] = []
    seen_canonical_keys: set[str] = set()

    for p in products:
        if not isinstance(p, dict):
            continue
        title = p.get('title')
        if not title:
            continue

        canon_key = get_canonical_title_key(title, str(p.get('brand') or ''))
        if canon_key and canon_key in seen_canonical_keys:
            continue

        # Check against already added products using full similarity check
        is_dup = False
        for existing in unique_products:
            if is_duplicate_product(p, existing):
                is_dup = True
                break

        if not is_dup:
            if canon_key:
                seen_canonical_keys.add(canon_key)
            unique_products.append(p)

    return unique_products
