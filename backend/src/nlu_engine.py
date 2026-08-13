"""
nlu_engine.py  –  NLU Engine
──────────────────────────────
Fixes v2:
  1. Audio type disambiguation — earbuds / earphones / headphones / neckband never mixed
  2. Feature extraction — processor, RAM, storage, camera MP, style, fit, fabric all extracted
  3. Vague query expansion — cheap/premium/camera/battery → concrete search hints
  4. Count handling — "suggest 2" → exactly 2; "t shirts 6" → 6; default 6
  5. Combined conditions — filter price FIRST, then rank by specs + brand + rating
  6. Multi-item detection — improved conjunctive split
  7. Variation — random search suffix for diverse results
"""

import re, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Entity tables ──────────────────────────────────────────────────────────────
COLORS = [
    'off white', 'navy blue', 'sky blue', 'dark green', 'light blue',
    'red', 'blue', 'green', 'black', 'white', 'pink', 'yellow', 'purple',
    'orange', 'grey', 'gray', 'silver', 'gold', 'brown', 'navy', 'beige',
    'maroon', 'cream', 'olive', 'teal', 'coral', 'khaki', 'lavender',
    'turquoise',
]

SIZES_CLOTHING = [
    'extra large', 'plus size', 'free size', 'xs', 's', 'm', 'l', 'xl',
    'xxl', 'xxxl', 'small', 'medium', 'large',
]

MATERIALS = [
    'leather', 'cotton', 'polyester', 'nylon', 'wool', 'silk', 'rubber',
    'plastic', 'metal', 'wood', 'glass', 'denim', 'velvet', 'suede',
    'canvas', 'linen', 'rayon', 'viscose', 'jute', 'fleece', 'mesh',
]

# ── Typo & Alias Normalization ──────────────────────────────────────────────────
TYPO_CORRECTIONS = [
    # Brands & Brand Aliases
    (r'\b(?:the\s*)?souled?\s*store\b', 'the souled store'),
    (r'\b(?:red\s*tape|redtape)\b', 'red tape'),
    (r'\b(?:boat|bo-at)\b', 'boat'),
    (r'\b(?:one\s*plus)\b', 'oneplus'),
    (r'\b(?:real\s*me)\b', 'realme'),
    (r'\b(?:fire\s*boltt|fireboltt)\b', 'fire-boltt'),

    # Audio Terms & Synonyms — earbuds variants (catches eardbuds, eardbud, etc.)
    # Pattern: any reasonable misspelling of "earbuds" with optional extra chars
    (r'\b(?:eard?buds?|earb[ou]ds?|earbdus?|earbubd?|eardbud|erbuds?'
     r'|ear\s*buds?|airpods?|air\s*pods?|airdopes?|air\s*dopes?|tws\s*buds?)\b', 'earbuds'),
    (r'\b(?:headphon|headphns?|head\s*phones?|head\s*set|overear|over-ear|on-ear)\b', 'headphones'),
    (r'\b(?:earphon|ear\s*phones?|wired\s*earphones?|earphn|earfon|earfons?)\b', 'earphones'),
    (r'\b(?:neck\s*band|neckbnd|neckbnd)\b', 'neckband'),

    # Common product typos
    (r'\b(?:batter|battry|batry|batery|battary|batterie)\b', 'battery'),
    (r'\b(?:prcessor|procssor|procosor|procesor)\b', 'processor'),
    (r'\b(?:camra|camer|camrea|camear)\b', 'camera'),
    (r'\b(?:gamng|gammig|gamin)\b', 'gaming'),
    (r'\b(?:tshirt|t\s*shirt|tee|tees)\b', 't-shirt'),
    (r'\b(?:snikers|sneaker|snickers)\b', 'sneakers'),
    (r'\b(?:smart\s*watch|smart-watch)\b', 'smartwatch'),
    (r'\b(?:laptap|lap\s*top|laptoop|laptopp|labtop)\b', 'laptop'),
    (r'\b(?:phon|mobi|mobil)\b', 'phone'),
    (r'\b(?:wirless|wirelss|wirelees|wirelass)\b', 'wireless'),
    (r'\b(?:bluethooth|bluetoth|bluethoth|blutooth|bluetooh)\b', 'bluetooth'),
    (r'\b(?:speker|speakr|speakar|speekar)\b', 'speaker'),
]

def normalize_spelling(q: str) -> str:
    cleaned = q.lower()
    for pattern, replacement in TYPO_CORRECTIONS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.I)
    return cleaned


# ── Audio type — STRICT mapping (never mix these) ──────────────────────────────
AUDIO_TYPE_PATTERNS = [
    ('neckband',    [r'\bneckband\b', r'\bneck\s*band\b']),
    ('earbuds',     [r'\bearbuds?\b', r'\btws\b', r'\bin[\s-]?ear\s+true\b', r'\bwireless\s+earbuds?\b', r'\bairpods?\b', r'\bair\s*pods?\b', r'\bairdopes?\b', r'\bair\s*dopes?\b', r'\bbuds\b']),
    ('earphones',   [r'\bearphones?\b', r'\bin[\s-]?ear\b(?!\s+true)', r'\bwired\s+earphones?\b']),
    ('headphones',  [r'\bheadphones?\b', r'\bover[\s-]?ear\b', r'\bon[\s-]?ear\b', r'\bheadset\b']),
    ('speaker',     [r'\bspeakers?\b', r'\bbluetooth\s+speaker\b', r'\bsoundbar\b']),
]


def _detect_audio_type(q: str) -> str | None:
    """Return exact audio product type or None. Never mixes types."""
    q_clean = normalize_spelling(q)
    for atype, patterns in AUDIO_TYPE_PATTERNS:
        for pat in patterns:
            if re.search(pat, q_clean, re.I):
                return atype
    return None


# Known brands — lowercase key → display name
KNOWN_BRANDS: dict[str, str] = {
    'the souled store': 'The Souled Store',
    'souled store': 'The Souled Store',
    'soul store': 'The Souled Store',
    'the soul store': 'The Souled Store',
    'red tape': 'Red Tape',
    'roadster': 'Roadster',
}
for _blist in config.INDIAN_BRANDS.values():
    for _b in _blist:
        KNOWN_BRANDS[_b.lower()] = _b

for _b in [
    'apple', 'samsung', 'sony', 'lg', 'hp', 'dell', 'lenovo', 'asus', 'acer',
    'nike', 'adidas', 'puma', 'reebok', 'skechers', 'bata', 'liberty', 'crocs',
    'canon', 'nikon', 'gopro', 'bose', 'jbl', 'sennheiser', 'skullcandy', 'jabra',
    'microsoft', 'intel', 'amd', 'nvidia', 'corsair', 'logitech', 'razer',
    'xiaomi', 'oneplus', 'realme', 'vivo', 'oppo', 'poco', 'iqoo', 'redmi',
    'motorola', 'boat', 'noise', 'fire-boltt', 'titan', 'fastrack', 'casio',
    'fossil', 'garmin', 'prestige', 'hawkins', 'pigeon', 'bajaj', 'philips',
    'panasonic', 'whirlpool', 'haier', 'godrej', 'voltas', 'daikin', 'lloyd',
    'patanjali', 'himalaya', 'dabur', 'mamaearth', 'plum', 'wow', 'mcaffeine',
    'lakme', 'maybelline', 'loreal', 'nykaa', 'minimalist',
    'decathlon', 'cosco', 'nivia', 'sg', 'yonex',
    'redgear', 'cosmic byte', 'ant esports', 'zebronics',
    'h&m', 'zara', 'mango', 'gap', 'levis', 'wrangler', 'lee', 'pepe jeans',
    'raymond', 'monte carlo', 'cantabil', 'blackberrys',
    'manyavar', 'fabindia', 'biba', 'libas', 'the souled store',
]:
    KNOWN_BRANDS[_b] = 'The Souled Store' if 'souled' in _b or 'soul' in _b else _b.title()

try:
    from src.query_understanding import BRAND_REGISTRY
    for _alias, _canonical in BRAND_REGISTRY.alias_to_canonical.items():
        KNOWN_BRANDS[_alias] = _canonical
except Exception:
    pass

# Category map: (keywords → category, dept, flipkart_dept)
# NOTE: Audio entries now use audio_type, not a catch-all
CATEGORY_MAP = [
    (['gaming laptop', 'gaming notebook', 'rtx laptop', 'gtx laptop'],
     'Electronics', 'Gaming Laptops', 'gaming-laptops'),
    (['laptop', 'notebook', 'ultrabook', 'chromebook', 'macbook', '2-in-1'],
     'Electronics', 'Laptops', 'laptops'),
    (['mobile', 'phone', 'smartphone', 'iphone', 'android', '5g phone', 'foldable'],
     'Cell_Phones_and_Accessories', 'Mobile Phones', 'mobiles'),
    # Audio — kept as fallback; audio_type extraction handles specifics
    (['earphone', 'earbuds', 'headphone', 'headset', 'neckband', 'tws'],
     'Electronics', 'Audio', 'earphones-headphones'),
    (['speaker', 'bluetooth speaker', 'soundbar', 'home theatre'],
     'Electronics', 'Speakers', 'speakers'),
    (['smartwatch', 'fitness band', 'fitness tracker', 'wearable'],
     'Electronics', 'Smartwatches', 'smart-wearable-tech'),
    (['television', 'led tv', 'smart tv', 'oled', 'qled', '4k tv'],
     'Electronics', 'Televisions', 'televisions'),
    (['camera', 'dslr', 'mirrorless', 'gopro', 'action camera', 'webcam'],
     'Electronics', 'Cameras', 'cameras'),
    (['t-shirt', 'tshirt', 'polo shirt', 't shirt'],
     'Clothing_Shoes_and_Jewelry', 'T-Shirts', 't-shirts'),
    (['shirt', 'formal shirt', 'casual shirt'],
     'Clothing_Shoes_and_Jewelry', 'Shirts', 'shirts'),
    (['jeans', 'denim', 'skinny jeans', 'slim fit jeans'],
     'Clothing_Shoes_and_Jewelry', 'Jeans', 'jeans'),
    (['trouser', 'pants', 'chinos', 'formal pant'],
     'Clothing_Shoes_and_Jewelry', 'Trousers', 'trousers'),
    (['kurta', 'kurti', 'salwar', 'saree', 'lehenga', 'ethnic wear', 'anarkali'],
     'Clothing_Shoes_and_Jewelry', 'Ethnic Wear', 'kurtas-and-suits'),
    (['dress', 'frock', 'maxi dress', 'mini dress', 'sundress'],
     'Clothing_Shoes_and_Jewelry', 'Dresses', 'dresses'),
    (['hoodie', 'sweatshirt', 'sweater', 'pullover'],
     'Clothing_Shoes_and_Jewelry', 'Sweatshirts', 'sweatshirts'),
    (['jacket', 'coat', 'blazer', 'windbreaker'],
     'Clothing_Shoes_and_Jewelry', 'Jackets', 'jackets'),
    (['shoes', 'sneakers', 'running shoes', 'sports shoes', 'formal shoes',
      'loafers', 'oxford', 'derby'],
     'Clothing_Shoes_and_Jewelry', 'Footwear', 'mens-footwear'),
    (['sandals', 'slippers', 'chappal', 'flip flops', 'heels', 'wedges'],
     'Clothing_Shoes_and_Jewelry', 'Sandals', 'womens-footwear'),
    (['bag', 'backpack', 'laptop bag', 'school bag'],
     'Clothing_Shoes_and_Jewelry', 'Bags', 'backpacks'),
    (['handbag', 'purse', 'clutch', 'sling bag', 'tote bag'],
     'Clothing_Shoes_and_Jewelry', 'Handbags', 'handbags'),
    (['watch', 'analog watch', 'digital watch', 'wrist watch'],
     'Clothing_Shoes_and_Jewelry', 'Watches', 'watches'),
    (['refrigerator', 'fridge'],
     'Home_and_Kitchen', 'Refrigerators', 'refrigerators'),
    (['washing machine', 'washer'],
     'Home_and_Kitchen', 'Washing Machines', 'washing-machines'),
    (['microwave', 'oven', 'otg'],
     'Home_and_Kitchen', 'Microwaves', 'microwave-ovens'),
    (['air conditioner', 'split ac', 'window ac'],
     'Home_and_Kitchen', 'Air Conditioners', 'air-conditioners'),
    (['mixer', 'grinder', 'blender', 'juicer', 'food processor'],
     'Home_and_Kitchen', 'Kitchen Appliances', 'mixer-grinder-juicers'),
    (['pressure cooker', 'cookware', 'induction cooktop', 'kadai'],
     'Home_and_Kitchen', 'Cookware', 'cookware'),
    (['cricket bat', 'cricket ball', 'cricket kit'],
     'Sports_and_Outdoors', 'Cricket', 'cricket'),
    (['dumbbell', 'barbell', 'gym equipment', 'protein', 'whey'],
     'Sports_and_Outdoors', 'Fitness', 'fitness'),
    (['yoga mat', 'yoga block'],
     'Sports_and_Outdoors', 'Yoga', 'yoga'),
    (['cycle', 'bicycle', 'mountain bike'],
     'Sports_and_Outdoors', 'Cycling', 'cycles'),
    (['gaming chair', 'gaming monitor', 'gaming keyboard', 'gaming mouse',
      'controller', 'joystick', 'ps5', 'xbox', 'nintendo'],
     'Video_Games', 'Gaming Accessories', 'gaming-accessories'),
    (['face wash', 'moisturiser', 'moisturizer', 'sunscreen', 'serum', 'toner'],
     'Health_and_Personal_Care', 'Skincare', 'skin-care'),
    (['shampoo', 'conditioner', 'hair oil', 'hair serum'],
     'Health_and_Personal_Care', 'Hair Care', 'hair-care'),
    (['perfume', 'deodorant', 'body spray', 'cologne', 'fragrance'],
     'Health_and_Personal_Care', 'Fragrances', 'fragrances'),
    (['vitamin', 'supplement', 'protein powder', 'health supplement'],
     'Health_and_Personal_Care', 'Health Supplements', 'health-supplements'),
]

# Fashion pairing map
FASHION_PAIRING = {
    't-shirt':  ['jeans', 'chinos', 'shorts', 'joggers', 'trousers'],
    'jeans':    ['t-shirt', 'shirt', 'kurta', 'hoodie', 'jacket', 'blazer'],
    'shirt':    ['jeans', 'chinos', 'trousers', 'shorts'],
    'kurta':    ['jeans', 'churidar', 'palazzo', 'leggings', 'salwar'],
    'saree':    ['blouse'],
    'dress':    ['heels', 'sandals', 'flats', 'jacket', 'blazer'],
    'shorts':   ['t-shirt', 'polo shirt', 'sneakers'],
    'leggings': ['kurta', 'tunic', 'long top'],
    'blazer':   ['shirt', 't-shirt', 'jeans', 'trousers'],
    'suit':     ['shirt', 'tie', 'formal shoes'],
    'sneakers': ['jeans', 'shorts', 'tracksuit'],
    'heels':    ['dress', 'saree', 'formal wear'],
    'hoodie':   ['jeans', 'joggers', 'chinos'],
}


# ── Tech spec patterns ─────────────────────────────────────────────────────────
TECH_SPECS = {
    'processor': [
        r'\bi[3579][-\s]?\d{4,5}\w*\b', r'\bryzen\s*[3579]\b',
        r'\bm[123]\s*(pro|max|ultra)?\b', r'\bceleron\b', r'\bpentium\b',
        r'\bsnap\w+\b', r'\bdimensity\b', r'\bhelio\b', r'\bmediatek\b',
    ],
    'ram': [
        r'\b(\d+)\s*gb\s*ram\b', r'\b(\d+)\s*gb\s*(?:lpddr|ddr)\d?\b',
        r'\b(\d+)\s*gb\s*memory\b',
    ],
    'storage': [
        r'\b(\d+)\s*(gb|tb)\s*(?:ssd|hdd|nvme|emmc|storage|rom|internal)\b',
        r'\b(\d+)\s*gb\s*(?:internal|rom)\b',
        r'\b(\d+)\s*tb\b',
    ],
    'display': [
        r'\b(\d+\.?\d*)["\']?\s*(?:inch|display|screen)\b',
        r'\b(fhd|qhd|4k|amoled|oled|ips|lcd|120hz|144hz|90hz|165hz)\b',
    ],
    'camera': [
        r'\b(\d+)\s*mp\b',
        r'\b(\d+)\s*mega\s*pixel\b',
        r'\b(triple|quad|dual)\s*camera\b',
        r'\b(ultrawide|telephoto|periscope)\b',
    ],
    'gpu': [
        r'\brtx\s*\d{3,4}\w*\b', r'\bgtx\s*\d{3,4}\w*\b', r'\brx\s*\d{3,4}\w*\b', r'\barc\s*\w+\b',
        r'\b(?:dedicated\s+)?graphics?\s*cards?\b', r'\bdedicated\s+(?:graphics?|gpu)\b',
        r'\bdiscrete\s+(?:graphics?|gpu)\b', r'\brtx\b', r'\bgtx\b',
    ],
}

# ── Fashion style / fit / occasion patterns ────────────────────────────────────
FASHION_STYLES = [
    'printed', 'solid', 'striped', 'checkered', 'floral', 'graphic', 'plain',
    'embroidered', 'tie-dye', 'abstract', 'geometric', 'polka dot',
]
FASHION_FIT = [
    'slim fit', 'regular fit', 'loose fit', 'oversized', 'skinny', 'relaxed',
    'straight fit', 'tapered', 'bootcut', 'baggy', 'slim',
]
FASHION_OCCASIONS = [
    'formal', 'casual', 'party', 'wedding', 'office', 'ethnic', 'sports',
    'gym', 'beach', 'festival', 'daily wear', 'workwear',
]

# ── Vague-query → concrete logic ───────────────────────────────────────────────
# Each entry maps a signal word to search-relevant expansions + NLU hints
VAGUE_SIGNALS = {
    'cheap':           {'price_tier': 'budget', 'vague_hint': 'budget affordable value for money'},
    'affordable':      {'price_tier': 'budget', 'vague_hint': 'budget affordable'},
    'budget':          {'price_tier': 'budget', 'vague_hint': 'budget value for money'},
    'inexpensive':     {'price_tier': 'budget', 'vague_hint': 'affordable low cost'},
    'premium':         {'price_tier': 'premium', 'vague_hint': 'premium high rated flagship'},
    'flagship':        {'price_tier': 'premium', 'vague_hint': 'flagship premium top of the line'},
    'luxury':          {'price_tier': 'premium', 'vague_hint': 'luxury premium exclusive'},
    'mid range':       {'price_tier': 'mid', 'vague_hint': 'mid range'},
    'mid-range':       {'price_tier': 'mid', 'vague_hint': 'mid range'},
    'camera phone':    {'feature_priority': 'camera', 'vague_hint': 'high megapixel camera best camera phone'},
    'best camera':     {'feature_priority': 'camera', 'vague_hint': 'high megapixel 108mp best camera'},
    'good camera':     {'feature_priority': 'camera', 'vague_hint': 'high megapixel camera'},
    'good battery':    {'feature_priority': 'battery', 'vague_hint': '5000mAh long battery life'},
    'long battery':    {'feature_priority': 'battery', 'vague_hint': '6000mAh battery endurance'},
    'big battery':     {'feature_priority': 'battery', 'vague_hint': '5000mAh 6000mAh battery'},
    'gaming':          {'feature_priority': 'gaming', 'vague_hint': 'gaming high performance'},
    'fast charging':   {'feature_priority': 'charging', 'vague_hint': '65W fast charging'},
    'lightweight':     {'feature_priority': 'weight', 'vague_hint': 'lightweight thin ultrabook'},
    'durable':         {'feature_priority': 'durability', 'vague_hint': 'rugged durable ip68'},
    'waterproof':      {'feature_priority': 'durability', 'vague_hint': 'waterproof ip68 ip67'},
}

# Price tier → implied budget ranges (INR)
PRICE_TIER_RANGES = {
    'budget':  (0,     15000),
    'mid':     (15000, 40000),
    'premium': (40000, 999999),
}

# Min-price for premium tier (for ranking filter)
PREMIUM_MIN_PRICE = 30000

# Multi-item separators (excluding 'with' which is used for feature descriptions)
_MULTI_ITEM_RE = re.compile(
    r'\b(?:and|&|\+|,|along with|plus)\b', re.I)


# ── Word-to-number helper ──────────────────────────────────────────────────────
_WORD_NUM = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}

DEFAULT_RESULT_COUNT = 6


def _parse_count(raw: str) -> int | None:
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw in _WORD_NUM:
        return _WORD_NUM[raw]
    try:
        return int(raw)
    except ValueError:
        return None


# ── Multi-item detection ───────────────────────────────────────────────────────
def _detect_multi_items(query: str) -> list[str]:
    """
    If query contains 2+ distinct product categories joined by conjunctions,
    return list of individual product dept names.
    """
    q = query.lower()
    parts = _MULTI_ITEM_RE.split(q)
    if len(parts) < 2:
        return []

    matched_cats = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        for kw_list, _cat, dept, _fk in CATEGORY_MAP:
            for kw in kw_list:
                if re.search(r'\b' + re.escape(kw) + r'\b', part):
                    if dept not in matched_cats:
                        matched_cats.append(dept)
                    break
            else:
                continue
            break

    return matched_cats if len(matched_cats) >= 2 else []


# ── Intent detector ────────────────────────────────────────────────────────────
def detect_intent(query: str) -> str:
    q = normalize_spelling(query.lower().strip())

    # 0. Multi-item — check first
    if _detect_multi_items(q):
        return 'multi_item'

    # 1. Comparison — multi-brand queries, "vs/versus/compare/compre", "which ... best/better ... or", "between"
    matched_brands = [b_name for b_lower, b_name in KNOWN_BRANDS.items() if re.search(r'\b' + re.escape(b_lower) + r'\b', q)]
    if len(matched_brands) >= 2:
        return 'comparison'

    if re.search(r'\bvs\.?\b|\bversus\b|\bcompare\b|\bcomparison\b|\bcompre\b|\bcomapre\b'
                 r'|\bwhich(?:\s+\w+)?\s+(?:is\s+)?(?:better|best)\b'
                 r'|\bbetter than\b'
                 r'|\bwhich (?:has|have|gives?|offer)\b'
                 r'|\bonly compare\b|\bjust compare\b'
                 r'|\bbetween\b', q):
        _PRODUCT_NOUNS = (r'phone|laptop|mobile|earbuds?|earphones?|headphones?|'
                          r'tablet|camera|watch|tv|shirt|jeans|shoes?|speaker|'
                          r'smartwatch|refrigerator|ac|cooler|cooker|bag|sneakers?')
        if (re.search(_PRODUCT_NOUNS, q) and len(matched_brands) >= 1 and re.search(r'\b(?:or|between|vs)\b', q)) \
                or re.search(r'\bvs\.?\b|\bversus\b|\bcompare\b|\bcompre\b|\bcomapre\b', q):
            return 'comparison'

    # 2. Fashion pairing
    if re.search(
        r'\bpair with\b|\bgo with\b|\bmatch with\b'
        r'|\bfor (?:a |my )?(?:' + '|'.join(FASHION_PAIRING.keys()) + r')\b'
        r'|\b(?:' + '|'.join(FASHION_PAIRING.keys()) + r') for\b', q):
        return 'pairing'
    if re.search(r'\bsuggest\b.+\b(?:jeans|shirt|kurta|shoes|jacket|top)\b.+\bfor\b', q):
        return 'pairing'

    # 3. Single best — "suggest/recommend 1" OR "one best X"
    if re.search(
        r'(?:suggest|recommend|give me|show me|find me)\s+(?:me\s+)?(?:1|one)\b'
        r'|(?:1|one)\s+best\b|best\s+(?:1|one)\b', q):
        return 'single_best'

    # 4. Price filter
    if re.search(r'\bunder\b|\bbelow\b|\bbudget\b|\bcheap\b|\baffordable\b'
                 r'|\bless than\b|\bwithin\b|\bupto\b|\bup to\b', q):
        return 'price_filter'

    # 5. Best / top
    if re.search(r'\bbest\b|\btop\b|\bpopular\b|\btrending\b|\bhighly rated\b'
                 r'|\bmost sold\b|\bbest selling\b', q):
        return 'best_in_category'

    # 6. Outfit / style
    if re.search(r'\boutfit\b|\blook\b|\bstyle\b|\bfashion\b|\bwhat to wear\b'
                 r'|\bcombo\b|\bcombination\b', q):
        return 'outfit'

    # 7. Recommendation
    if re.search(r'\brecommend\b|\badvise\b|\bsuggestion\b|\bshould i buy\b'
                 r'|\bworth buying\b|\bwhich one to buy\b', q):
        return 'recommendation'

    # 8. Explicit count suggestion — "suggest N phones"
    if re.search(
        r'(?:suggest|recommend|show|give|find)\s+(?:me\s+)?'
        r'(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b', q):
        return 'product_search'

    # 9. Pure info — only when no product/brand is in the query
    if re.search(r'\bhow to\b|\bhow do\b|\bsteps to\b|\bguide\b'
                 r'|\bwhat is\b|\bwhat are\b|\bexplain\b|\bmeaning of\b', q):
        return 'info_only'

    # 10. Tech spec
    if re.search(r'\bgpu\b|\brtx\b|\bgtx\b|\bram\b|\bprocessor\b|\bspec\b'
                 r'|\bperformance\b|\bbenchmark\b', q):
        return 'tech_spec'

    # 11. Price query
    if re.search(r'\bhow much\b|\bprice of\b|\bcost of\b|\brate of\b', q):
        return 'price_query'

    return 'product_search'


# ── Entity extractor ───────────────────────────────────────────────────────────
def extract_entities(query: str) -> dict:
    q = normalize_spelling(query.lower())

    ents: dict = {
        'brands':           [],
        'colors':           [],
        'sizes':            [],
        'materials':        [],
        'category':         None,
        'dept':             None,
        'flipkart_dept':    None,
        'max_price':        None,
        'min_price':        None,
        'gender':           None,
        'count':            None,
        'pairing_item':     None,
        'pairing_color':    None,
        'gaming':           False,
        'wireless':         False,
        'waterproof':       False,
        'audio_type':       None,   # ← NEW: earbuds|earphones|headphones|neckband|speaker
        'tech_specs':       {},
        'fashion_styles':   [],
        'feature_priority': None,
        'price_tier':       None,
        'min_price_tier':   None,
        'vague_hint':       '',     # ← extra search terms from vague signals
        'multi_items':      [],
    }

    # ── Audio type — MUST be detected before category (prevents mixing) ─────────
    ents['audio_type'] = _detect_audio_type(q)

    # ── Brands — whole-word match only ──────────────────────────────────────────
    found = []
    for b_lower, b_display in KNOWN_BRANDS.items():
        pattern = r'(?<![a-z])' + re.escape(b_lower) + r'(?![a-z])'
        if re.search(pattern, q) and b_display not in found:
            found.append(b_display)
    ents['brands'] = found

    # ── Colors — longest match first ────────────────────────────────────────────
    found_colors = []
    q_tmp = q
    for c in sorted(COLORS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(c) + r'\b', q_tmp):
            found_colors.append(c)
            q_tmp = q_tmp.replace(c, '')
    ents['colors'] = found_colors

    # ── Sizes ────────────────────────────────────────────────────────────────────
    ents['sizes'] = [s for s in SIZES_CLOTHING
                     if re.search(r'\b' + re.escape(s) + r'\b', q)]

    # ── Materials / Fabric ───────────────────────────────────────────────────────
    ents['materials'] = [m for m in MATERIALS
                         if re.search(r'\b' + re.escape(m) + r'\b', q)]

    # ── Price extraction ─────────────────────────────────────────────────────────
    pm = re.search(
        r'(?:under|below|less than|upto?|up to|within|max(?:imum)?|budget of?)'
        r'\s*[₹₨$rs\.]*\s*(\d[\d,]*)\s*(?:k\b|thousand\b)?',
        q, re.I)
    if pm:
        raw_price = pm.group(1).replace(',', '')
        val = int(raw_price)
        suffix = pm.group(0).lower()
        if suffix.endswith('k') or 'thousand' in suffix:
            val *= 1000
        ents['max_price'] = val

    # ── Gender ───────────────────────────────────────────────────────────────────
    if re.search(r"\bwomen'?s?\b|\bfemale\b|\bgirls?\b|\bladie?s?\b|\bher\b", q):
        ents['gender'] = 'women'
    elif re.search(r"\bmen'?s?\b|\bmale\b|\bboys?\b|\bgent'?s?\b|\bhis\b", q):
        ents['gender'] = 'men'
    elif re.search(r'\bkids?\b|\bchild\b|\bchildren\b|\bbaby\b|\btoddler\b', q):
        ents['gender'] = 'kids'
    elif re.search(r'\bunisex\b', q):
        ents['gender'] = 'unisex'

    # ── Count extraction — comprehensive patterns ────────────────────────────────
    # Pattern 1: "suggest/show/give/recommend/find me N X"
    cm1 = re.search(
        r'(?:suggest|show|find|recommend|give|get)\s+(?:me\s+)?'
        r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b',
        q)
    # Pattern 2: "N best/top X"
    cm2 = re.search(
        r'\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:best|top|good|great)\b',
        q)
    # Pattern 3: bare "X N" at end, e.g. "t shirts 6"
    cm3 = re.search(
        r'(?:shirts?|phones?|laptops?|shoes?|earbuds?|headphones?|kurtas?|jeans|products?)'
        r'\s+(\d+)\s*$',
        q)

    raw_n = None
    if cm1:
        raw_n = cm1.group(1)
    elif cm2:
        raw_n = cm2.group(1)
    elif cm3:
        raw_n = cm3.group(1)

    if raw_n:
        ents['count'] = _parse_count(raw_n)

    # ── Fashion pairing ──────────────────────────────────────────────────────────
    pair_match = re.search(
        r'\bfor\s+(?:a\s+)?(?:my\s+)?'
        r'(' + '|'.join(COLORS) + r')?\s*'
        r'(' + '|'.join(re.escape(k) for k in FASHION_PAIRING.keys()) + r')\b', q)
    if pair_match:
        ents['pairing_color'] = pair_match.group(1) or None
        ents['pairing_item']  = pair_match.group(2) or None

    # ── Category — first match wins ──────────────────────────────────────────────
    # If audio_type is set, map to the right dept directly
    if ents['audio_type']:
        _AUDIO_DEPT_MAP = {
            'earbuds':    ('Electronics', 'Earbuds', 'earphones-headphones'),
            'earphones':  ('Electronics', 'Earphones', 'earphones-headphones'),
            'headphones': ('Electronics', 'Headphones', 'earphones-headphones'),
            'neckband':   ('Electronics', 'Neckband', 'earphones-headphones'),
            'speaker':    ('Electronics', 'Speakers', 'speakers'),
        }
        cat, dept, fk = _AUDIO_DEPT_MAP[ents['audio_type']]
        ents['category']      = cat
        ents['dept']          = dept
        ents['flipkart_dept'] = fk
    else:
        for kw_list, cat, dept, fk_dept in CATEGORY_MAP:
            if any(re.search(r'\b' + re.escape(kw) + r'(?:es|s)?\b', q) for kw in kw_list):
                ents['category']      = cat
                ents['dept']          = dept
                ents['flipkart_dept'] = fk_dept
                break

    # ── Feature flags ────────────────────────────────────────────────────────────
    ents['gaming']     = bool(re.search(r'\bgaming\b', q))
    ents['wireless']   = bool(re.search(r'\bwireless\b|\bbluetooth\b', q))
    ents['waterproof'] = bool(re.search(r'\bwaterproof\b|\bwater[\s-]?resist', q))

    # ── Tech spec extraction ──────────────────────────────────────────────────────
    tech = {}
    for spec, patterns in TECH_SPECS.items():
        for pat in patterns:
            m = re.search(pat, q, re.I)
            if m:
                tech[spec] = m.group(0).strip()
                break
    ents['tech_specs'] = tech

    # ── Fashion feature extraction ────────────────────────────────────────────────
    styles = []
    for s in FASHION_FIT:
        if re.search(r'\b' + re.escape(s) + r'\b', q):
            styles.append(s)
    for s in FASHION_STYLES:
        if s == 'graphic' and re.search(r'\bgraphic\s*(?:card|cards|memory|driver|display|gpu|graphics)\b', q, re.I):
            continue
        if re.search(r'\b' + re.escape(s) + r'\b', q):
            styles.append(s)
    for s in FASHION_OCCASIONS:
        if re.search(r'\b' + re.escape(s) + r'\b', q):
            styles.append(s)
    ents['fashion_styles'] = styles

    # ── Vague query signals ───────────────────────────────────────────────────────
    vague_hints = []
    for signal, props in VAGUE_SIGNALS.items():
        if re.search(r'\b' + re.escape(signal) + r'\b', q, re.I):
            for k, v in props.items():
                if k == 'vague_hint':
                    vague_hints.append(v)
                elif not ents.get(k):
                    ents[k] = v

    ents['vague_hint'] = ' '.join(vague_hints)

    # Apply price tier → price bounds only for expensive electronics (Laptops, Phones, TVs)
    is_expensive_electronics = ents.get('dept') in ('Laptops', 'Gaming Laptops', 'Mobile Phones', 'Televisions')

    if ents.get('price_tier') and not ents.get('max_price'):
        _lo, _hi = PRICE_TIER_RANGES.get(ents['price_tier'], (0, 0))
        if _hi and _hi < 999999:
            if is_expensive_electronics:
                ents['max_price'] = _hi
            elif ents['price_tier'] == 'budget':
                # e.g. budget clothes/shoes under 1500 INR
                ents['max_price'] = 1500
        if _lo and is_expensive_electronics:
            ents['min_price'] = _lo
    # Premium tier — apply min price for ranking even if max_price also set
    if ents.get('price_tier') == 'premium' and is_expensive_electronics:
        ents['min_price'] = ents.get('min_price') or PREMIUM_MIN_PRICE

    # ── Multi-item detection ──────────────────────────────────────────────────────
    ents['multi_items'] = _detect_multi_items(q)

    # Save the custom extracted descriptive product name
    ents['product_name'] = _extract_product_name(q, ents)

    return ents


# ── Build search queries ───────────────────────────────────────────────────────
def _clean_q(q: str) -> str:
    q = re.sub(
        r'^(?:find me|show me|get me|suggest|recommend|search for|i want|i need|'
        r'looking for|give me|can you|please|tell me)\s+', '', q.lower().strip())
    return q.strip()


def _build_tokens(*parts) -> str:
    joined = ' '.join(str(p) for p in parts if p)
    joined = re.sub(r'\s+', ' ', joined).strip()
    words = joined.split()
    deduped = [words[0]] if words else []
    for w in words[1:]:
        if w.lower() != deduped[-1].lower():
            deduped.append(w)
    return ' '.join(deduped)


def _india(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    return s if 'india' in s.lower() else s + ' India'


def _tech_token(tech: dict) -> str:
    """Build a concise tech spec string for search queries."""
    parts = []
    for spec in ('processor', 'ram', 'storage', 'gpu', 'display', 'camera', 'battery'):
        val = tech.get(spec)
        if val:
            parts.append(val)
    return ' '.join(parts)


def _style_token(styles: list) -> str:
    """Top 2 fashion styles joined."""
    return ' '.join(styles[:2]) if styles else ''


def _extract_product_name(q: str, ents: dict) -> str:
    """
    Extract the specific product descriptive terms from the user query.
    Removes extracted brands, colors, prices, specs, vague words, and filler words.
    Falls back to audio_type or broad department name only when query has no specific product nouns.
    """
    p = q.lower()
    
    # Remove extracted brands
    for b in ents.get('brands', []):
        p = re.sub(r'\b' + re.escape(b.lower()) + r'\b', '', p)
        
    # Remove extracted colors
    for c in ents.get('colors', []):
        p = re.sub(r'\b' + re.escape(c.lower()) + r'\b', '', p)
        
    # Remove price phrases (e.g., "under 500", "below 1000", "₹500", "50k")
    p = re.sub(r'\b(?:under|below|less\s+than|upto?|up\s+to|within|max|budget\s+of?)\s*[₹₨$rs\.]*\s*\d[\d,]*\s*(?:k\b|thousand\b)?', '', p)
    p = re.sub(r'\b\d[\d,]*\s*(?:k\b|thousand\b)?\b', '', p)
    
    # Remove tech spec tokens from product term to prevent duplication
    p = re.sub(r'\b(?:i[3579]|ryzen\s*[3579]?|core\s*ultra|intel|amd|nvidia|rtx\s*\d*|gtx\s*\d*|processor|cpu|ram|\d+\s*gb|\d+\s*tb|ssd|hdd|storage|graphics?\s*cards?|dedicated\s*graphics?|dedicated\s*gpu|gpu|graphics?|anc)\b', '', p, flags=re.I)

    # Remove vague signal words
    for signal in VAGUE_SIGNALS:
        p = re.sub(r'\b' + re.escape(signal) + r'\b', '', p)
        
    # Remove general fillers and introductory words
    p = re.sub(r'\b(?:best|top|latest|suggest|recommend|show|find|get|me|i\s+want|i\s+need|looking\s+for|please|pls|india)\b', '', p)
    
    # Clean whitespace
    p = re.sub(r'\s+', ' ', p).strip()
    
    # If we have a valid descriptive term, use it!
    if p and len(p) >= 3:
        return p
        
    # Fallback to audio_type or dept if nothing remains
    return ents.get('audio_type') or ents.get('dept') or 'product'


# Variation suffixes for diverse results (rotated randomly)
_VARIATION_SUFFIXES = ['top rated', 'best seller', 'highly rated', 'popular', '']


def build_search_queries(query: str, intent: str, ents: dict) -> list[dict]:
    """
    Returns list of {'label': str, 'query': str}.
    Incorporates audio_type, tech specs, fashion styles, and vague hints.
    """
    q        = _clean_q(query)
    brands   = ents.get('brands', [])
    colors   = ents.get('colors', [])
    gender   = ents.get('gender') or ''
    dept     = ents.get('dept') or ''
    price    = ents.get('max_price')
    price_s  = f"under ₹{price:,}" if price else ''
    color_s  = colors[0] if colors else ''
    tech_s   = _tech_token(ents.get('tech_specs', {}))
    style_s  = _style_token(ents.get('fashion_styles', []))
    audio_t  = ents.get('audio_type') or ''
    vague_s  = ents.get('vague_hint', '')

    # Use extracted product keywords as primary product term when set (falls back to audio_t/dept)
    product_term = _extract_product_name(q, ents)

    # ── MULTI-ITEM: one query per product category ────────────────────────────
    if intent == 'multi_item':
        multi = ents.get('multi_items', [])
        if multi:
            return [
                {'label': cat_dept, 'query': _india(_build_tokens(
                    gender, cat_dept, color_s, price_s))}
                for cat_dept in multi
            ]

    # ── COMPARISON: one query per brand ───────────────────────────────────────
    if intent == 'comparison':
        if len(brands) >= 2:
            product_type = q
            for b in brands:
                product_type = re.sub(r'\b' + re.escape(b.lower()) + r'\b', '', product_type)
            product_type = re.sub(
                r'\b(?:vs\.?|versus|compare|comparison|difference between|'
                r'which is better|better than)\b', '', product_type)
            product_type = re.sub(r'\s+', ' ', product_type).strip()
            if not product_type:
                product_type = product_term or 'product'

            return [
                {'label': b,
                 'query': _india(_build_tokens(b, tech_s, product_type, price_s))}
                for b in brands
            ]
        elif len(brands) == 1:
            product_type = re.sub(r'\b' + re.escape(brands[0].lower()) + r'\b', '', q)
            product_type = re.sub(r'\b(?:vs\.?|versus|compare)\b', '', product_type).strip()
            return [{'label': brands[0],
                     'query': _india(_build_tokens(brands[0], tech_s, product_type, 'review'))}]
        else:
            return [{'label': 'Comparison', 'query': _india(q)}]

    # ── PAIRING ────────────────────────────────────────────────────────────────
    if intent == 'pairing':
        pairing_item  = ents.get('pairing_item')
        pairing_color = ents.get('pairing_color') or ''

        if pairing_item and pairing_item in FASHION_PAIRING:
            complements = FASHION_PAIRING[pairing_item]
            asked_item = dept or complements[0]
            g = gender or ''
            return [{'label': 'Pairing',
                     'query': _india(_build_tokens(
                         color_s, g, asked_item, 'for', pairing_color, pairing_item, price_s))}]

        return [{'label': 'Pairing', 'query': _india(_build_tokens(q, price_s))}]

    # ── SINGLE BEST ────────────────────────────────────────────────────────────
    if intent == 'single_best':
        brand_s = brands[0] if brands else ''
        return [{'label': 'Top Pick',
                 'query': _india(_build_tokens(
                     brand_s, tech_s, color_s, gender, style_s, product_term or q, price_s))}]

    # ── INFO ONLY ──────────────────────────────────────────────────────────────
    if intent == 'info_only':
        return []

    # ── All other intents ──────────────────────────────────────────────────────
    brand_s = brands[0] if brands else ''

    # Add variation to avoid identical results on repeated queries
    variation = random.choice(_VARIATION_SUFFIXES) if not brands else ''

    base = _build_tokens(
        brand_s,
        tech_s,
        color_s, gender, style_s,
        product_term or q,
        vague_s,          # ← vague expansion terms injected here
        price_s,
        variation,
    )
    return [{'label': 'Results', 'query': _india(base)}]


# ── Public API ─────────────────────────────────────────────────────────────────
def analyse(query: str) -> dict:
    intent  = detect_intent(query)
    ents    = extract_entities(query)
    queries = build_search_queries(query, intent, ents)
    return {
        'intent':   intent,
        'entities': ents,
        'queries':  queries,
    }