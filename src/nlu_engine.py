"""
nlu_engine.py  –  NLU Engine
──────────────────────────────
Fixes:
  1. Comparison regex — no longer false-matches price ranges with "or"
  2. Query builder — no more duplicate/messy tokens in search strings
  3. Price extraction — handles ₹15000, 15k, 15,000, "15 thousand"
  4. Brand matching — whole-word only, prevents partial matches
  5. Count extraction — only matches when followed by intent word
"""

import re, os, sys
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

# Known brands — lowercase key → display name
KNOWN_BRANDS: dict[str, str] = {}
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
    'manyavar', 'fabindia', 'biba', 'libas',
]:
    KNOWN_BRANDS[_b] = _b.title()

# Category map: (keywords → category, dept, flipkart_dept)
CATEGORY_MAP = [
    (['gaming laptop', 'gaming notebook', 'rtx laptop', 'gtx laptop'],
     'Electronics', 'Gaming Laptops', 'gaming-laptops'),
    (['laptop', 'notebook', 'ultrabook', 'chromebook', 'macbook', '2-in-1'],
     'Electronics', 'Laptops', 'laptops'),
    (['mobile', 'phone', 'smartphone', 'iphone', 'android', '5g phone', 'foldable'],
     'Cell_Phones_and_Accessories', 'Mobile Phones', 'mobiles'),
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
    (['t-shirt', 'tshirt', 'polo shirt'],
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


# ── Intent detector ────────────────────────────────────────────────────────────
def detect_intent(query: str) -> str:
    q = query.lower().strip()

    # 1. Comparison — strict: needs "vs/versus/compare" OR "which is better"
    #    Avoid matching "over X or under Y" price ranges
    if re.search(r'\bvs\.?\b|\bversus\b|\bcompare\b|\bcomparison\b'
                 r'|\bwhich is better\b|\bbetter than\b', q):
        return 'comparison'

    # 2. Fashion pairing
    if re.search(
        r'\bpair with\b|\bgo with\b|\bmatch with\b'
        r'|\bfor (?:a |my )?(?:' + '|'.join(FASHION_PAIRING.keys()) + r')\b'
        r'|\b(?:' + '|'.join(FASHION_PAIRING.keys()) + r') for\b', q):
        return 'pairing'
    if re.search(r'\bsuggest\b.+\b(?:jeans|shirt|kurta|shoes|jacket|top)\b.+\bfor\b', q):
        return 'pairing'

    # 3. Single best — must explicitly say "1/one best" or "suggest 1"
    if re.search(
        r'\b(?:suggest|recommend|give me|show me|find me)\b.{0,20}\b(?:1|one)\b'
        r'|\b(?:1|one)\s+best\b|\bbest\s+(?:1|one)\b', q):
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

    # 8. Pure info — only when no product/brand is in the query
    if re.search(r'\bhow to\b|\bhow do\b|\bsteps to\b|\bguide\b'
                 r'|\bwhat is\b|\bwhat are\b|\bexplain\b|\bmeaning of\b', q):
        return 'info_only'

    # 9. Tech spec
    if re.search(r'\bgpu\b|\brtx\b|\bgtx\b|\bram\b|\bprocessor\b|\bspec\b'
                 r'|\bperformance\b|\bbenchmark\b', q):
        return 'tech_spec'

    # 10. Price query
    if re.search(r'\bhow much\b|\bprice of\b|\bcost of\b|\brate of\b', q):
        return 'price_query'

    return 'product_search'


# ── Entity extractor ───────────────────────────────────────────────────────────
def extract_entities(query: str) -> dict:
    q = query.lower()

    ents: dict = {
        'brands':        [],
        'colors':        [],
        'sizes':         [],
        'materials':     [],
        'category':      None,
        'dept':          None,
        'flipkart_dept': None,
        'max_price':     None,
        'gender':        None,
        'count':         None,
        'pairing_item':  None,
        'pairing_color': None,
        'gaming':        False,
        'wireless':      False,
        'waterproof':    False,
    }

    # Brands — whole-word match only to avoid partial hits
    found = []
    for b_lower, b_display in KNOWN_BRANDS.items():
        pattern = r'(?<![a-z])' + re.escape(b_lower) + r'(?![a-z])'
        if re.search(pattern, q) and b_display not in found:
            found.append(b_display)
    ents['brands'] = found

    # Colors — longest match first to catch "navy blue" before "blue"
    found_colors = []
    q_tmp = q
    for c in sorted(COLORS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(c) + r'\b', q_tmp):
            found_colors.append(c)
            q_tmp = q_tmp.replace(c, '')   # prevent double-match
    ents['colors'] = found_colors

    # Sizes
    ents['sizes'] = [s for s in SIZES_CLOTHING
                     if re.search(r'\b' + re.escape(s) + r'\b', q)]

    # Materials
    ents['materials'] = [m for m in MATERIALS
                         if re.search(r'\b' + re.escape(m) + r'\b', q)]

    # Price — handles: under ₹15000, under 15k, under 15,000, under 15 thousand
    pm = re.search(
        r'(?:under|below|less than|upto?|up to|within|max(?:imum)?|budget of?)'
        r'\s*[₹₨$rs\.]*\s*(\d[\d,]*)\s*(?:k\b|thousand\b)?',
        q, re.I)
    if pm:
        raw_price = pm.group(1).replace(',', '')
        val = int(raw_price)
        # handle "15k" / "15 thousand"
        suffix = pm.group(0).lower()
        if suffix.endswith('k') or 'thousand' in suffix:
            val *= 1000
        ents['max_price'] = val

    # Gender
    if re.search(r"\bwomen'?s?\b|\bfemale\b|\bgirls?\b|\bladie?s?\b|\bher\b", q):
        ents['gender'] = 'women'
    elif re.search(r"\bmen'?s?\b|\bmale\b|\bboys?\b|\bgent'?s?\b|\bhis\b", q):
        ents['gender'] = 'men'
    elif re.search(r'\bkids?\b|\bchild\b|\bchildren\b|\bbaby\b|\btoddler\b', q):
        ents['gender'] = 'kids'
    elif re.search(r'\bunisex\b', q):
        ents['gender'] = 'unisex'

    # Count — only when followed by "best/top/good/great" or preceded by "suggest/show"
    cm = re.search(
        r'(?:suggest|show|find|recommend|give)\s+(?:me\s+)?(\d+|one|two|three|four|five)'
        r'|(\d+|one|two|three|four|five)\s+(?:best|top|good|great)',
        q)
    if cm:
        raw_n = (cm.group(1) or cm.group(2) or '').strip()
        word_to_num = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
        ents['count'] = word_to_num.get(raw_n, int(raw_n) if raw_n.isdigit() else None)

    # Fashion pairing
    pair_match = re.search(
        r'\bfor\s+(?:a\s+)?(?:my\s+)?'
        r'(' + '|'.join(COLORS) + r')?\s*'
        r'(' + '|'.join(re.escape(k) for k in FASHION_PAIRING.keys()) + r')\b', q)
    if pair_match:
        ents['pairing_color'] = pair_match.group(1) or None
        ents['pairing_item']  = pair_match.group(2) or None

    # Category — first match wins
    for kw_list, cat, dept, fk_dept in CATEGORY_MAP:
        if any(re.search(r'\b' + re.escape(kw) + r'\b', q) for kw in kw_list):
            ents['category']      = cat
            ents['dept']          = dept
            ents['flipkart_dept'] = fk_dept
            break

    # Flags
    ents['gaming']     = bool(re.search(r'\bgaming\b', q))
    ents['wireless']   = bool(re.search(r'\bwireless\b|\bbluetooth\b', q))
    ents['waterproof'] = bool(re.search(r'\bwaterproof\b|\bwater[\s-]?resist', q))

    return ents


# ── Build search queries ───────────────────────────────────────────────────────
def _clean_q(q: str) -> str:
    """Strip filler words from the start of a query."""
    q = re.sub(
        r'^(?:find me|show me|get me|suggest|recommend|search for|i want|i need|'
        r'looking for|give me|can you|please|tell me)\s+', '', q.lower().strip())
    return q.strip()


def _build_tokens(*parts) -> str:
    """Join parts, collapse whitespace, deduplicate adjacent words."""
    joined = ' '.join(str(p) for p in parts if p)
    joined = re.sub(r'\s+', ' ', joined).strip()
    # remove duplicate consecutive words
    words = joined.split()
    deduped = [words[0]] if words else []
    for w in words[1:]:
        if w != deduped[-1]:
            deduped.append(w)
    return ' '.join(deduped)


def _india(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    return s if 'india' in s.lower() else s + ' India'


def build_search_queries(query: str, intent: str, ents: dict) -> list[dict]:
    """
    Returns list of {'label': str, 'query': str}.
    Each query is clean, deduplicated, and ends with 'India'.
    """
    q       = _clean_q(query)
    brands  = ents.get('brands', [])
    colors  = ents.get('colors', [])
    gender  = ents.get('gender') or ''
    dept    = ents.get('dept') or ''
    price   = ents.get('max_price')
    price_s = f"under ₹{price:,}" if price else ''
    color_s = colors[0] if colors else ''   # use first color only

    # ── COMPARISON: one query per brand ───────────────────────────────────────
    if intent == 'comparison':
        if len(brands) >= 2:
            # Strip brand names and comparison words to get product type
            product_type = q
            for b in brands:
                product_type = re.sub(r'\b' + re.escape(b.lower()) + r'\b', '', product_type)
            product_type = re.sub(
                r'\b(?:vs\.?|versus|compare|comparison|difference between|'
                r'which is better|better than)\b', '', product_type)
            product_type = re.sub(r'\s+', ' ', product_type).strip()
            if not product_type:
                product_type = dept or 'product'

            return [
                {'label': b,
                 'query': _india(_build_tokens('best', b, product_type, price_s))}
                for b in brands
            ]
        elif len(brands) == 1:
            product_type = re.sub(r'\b' + re.escape(brands[0].lower()) + r'\b', '', q)
            product_type = re.sub(r'\b(?:vs\.?|versus|compare)\b', '', product_type).strip()
            return [{'label': brands[0],
                     'query': _india(_build_tokens(brands[0], product_type, 'review'))}]
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
                     'best', color_s, gender, dept or q, brand_s, price_s))}]

    # ── INFO ONLY ──────────────────────────────────────────────────────────────
    if intent == 'info_only':
        return []   # no live search

    # ── All other intents ──────────────────────────────────────────────────────
    brand_s = brands[0] if brands else ''   # use first brand only in query
    base = _build_tokens(color_s, gender, dept or q, brand_s, price_s)
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
