"""
response_builder.py  –  Response Builder
──────────────────────────────────────────
Fixes:
  1. _comparison_response — safe index access, no crash on 1 brand
  2. _listing_response    — clean heading, no double spaces
  3. _info_response       — actually useful topic-aware answers
  4. _pairing_response    — handles empty product list gracefully
  5. All responses        — consistent ₹ formatting and tips
"""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# ── Small helpers ──────────────────────────────────────────────────────────────
def _price_s(ents: dict) -> str:
    mp = ents.get('max_price')
    return f" under ₹{mp:,}" if mp else ""


def _color_s(ents: dict) -> str:
    c = ents.get('colors', [])
    return c[0].title() if c else ''


def _gender_s(ents: dict) -> str:
    return {
        'women':  "Women's",
        'men':    "Men's",
        'kids':   "Kids'",
        'unisex': "Unisex",
    }.get(ents.get('gender', ''), '')


def _dept(ents: dict) -> str:
    return ents.get('dept') or 'products'


def _clean_heading(*parts) -> str:
    """Join parts, collapse whitespace — prevents double-space headings."""
    joined = ' '.join(str(p) for p in parts if p)
    return re.sub(r'\s+', ' ', joined).strip()


# ── Info-only responses ────────────────────────────────────────────────────────
_HOW_TO_TIPS = {
    'clean leather shoes':  "Use a soft damp cloth to wipe off dirt, then apply leather conditioner. Avoid soaking in water.",
    'choose laptop':        "Consider: processor (i5/Ryzen 5+), RAM (16GB), display (FHD), battery life, and budget.",
    'choose phone':         "Check: processor benchmarks, camera samples, battery capacity, and after-sales service in India.",
    'choose earbuds':       "Look for: ANC (Active Noise Cancellation), battery life, IP rating, and codec support (aptX/AAC).",
    'choose gaming laptop': "Prioritise: GPU (RTX 4060+), 16GB RAM, 144Hz display, thermal performance, and weight.",
    'choose dslr':          "For beginners: Canon 1500D or Nikon D3500. Key factors: sensor size, kit lens, battery life.",
    'clean shoes':          "Remove laces, brush off dirt, use shoe cleaner with a soft brush, air dry away from sunlight.",
    'choose refrigerator':  "Consider: capacity (litres), star rating for energy efficiency, frost-free vs. direct cool, brand warranty.",
    'choose ac':            "Look for: 5-star BEE rating, inverter technology, brand service network, and BTU for your room size.",
}


def _info_response(query: str, ents: dict) -> str:
    q    = query.lower()
    dept = _dept(ents)

    # How-to — try to match known tips
    if re.search(r'\bhow to\b|\bhow do\b|\bsteps to\b', q):
        topic_raw = re.sub(r'\bhow (to|do i?)\b', '', q).strip()

        # Check for a matching tip
        for key, tip in _HOW_TO_TIPS.items():
            if all(word in topic_raw for word in key.split()):
                return (
                    f"**How to {topic_raw.title()}**\n\n"
                    f"{tip}\n\n"
                    f"💡 Want to **buy** {dept}? Just ask me to find or recommend one — "
                    f"I'll pull live ₹ prices from Indian stores like Flipkart and Amazon.in."
                )

        # Generic how-to
        return (
            f"**How to {topic_raw.title()}**\n\n"
            f"Here are the key steps for *{topic_raw}*:\n"
            f"- Research the options available in India\n"
            f"- Compare brands by ratings and reviews\n"
            f"- Check warranty and after-sales support\n"
            f"- Buy from trusted stores: Flipkart, Amazon.in, Croma\n\n"
            f"💡 Want me to **find** or **recommend** {dept}? Just ask!"
        )

    # What is / explain
    if re.search(r'\bwhat is\b|\bwhat are\b|\bexplain\b|\bmeaning of\b', q):
        topic = re.sub(r'\bwhat (?:is|are)\b|\bexplain\b|\bmeaning of\b', '', q).strip()
        return (
            f"**{topic.title()}** is a popular product category in {dept}.\n\n"
            f"To get detailed specs and live ₹ prices, ask me to:\n"
            f"- 🔍 *\"Find {topic} under ₹X\"*\n"
            f"- ⚖️ *\"Compare [Brand A] vs [Brand B] {topic}\"*\n"
            f"- 🥇 *\"Suggest 1 best {topic}\"*\n\n"
            f"I'll fetch real listings from Flipkart, Amazon.in and more."
        )

    # Difference without brands
    if re.search(r'\bdifference\b', q) and not ents.get('brands'):
        return (
            "I can compare specific brands for you! Try:\n"
            "- *\"Compare Dell vs HP laptop\"*\n"
            "- *\"Realme vs Vivo phone for gaming\"*\n"
            "- *\"Nike vs Adidas running shoes\"*\n\n"
            "I'll show you side-by-side options with live ₹ prices."
        )

    return (
        "That's a great question! For specific product help, ask me to **find**, "
        "**recommend**, or **compare** — I'll pull live Indian store results with ₹ prices.\n\n"
        f"Try: *\"Best {dept} under ₹10,000\"* or *\"Top {dept} in India\"*"
    )


# ── Comparison response ────────────────────────────────────────────────────────
def _comparison_response(
    brands_data: dict[str, list], ents: dict, query: str
) -> tuple[str, list]:
    brands = list(brands_data.keys())
    dept   = _dept(ents)
    price  = _price_s(ents)

    if not brands:
        return (
            "I couldn't find results for the comparison. "
            "Try mentioning both brand names clearly — e.g. *\"Realme vs Samsung phone\"*.",
            []
        )

    lines = [f"## ⚖️ {' vs '.join(brands)} — {dept.title()} Comparison{price}\n"]

    all_products: list = []
    counts: list[int] = []

    for brand, products in brands_data.items():
        counts.append(len(products))
        if products:
            best = products[0]
            rating_s = f" ⭐ {best['rating']}" if best.get('rating') else ''
            lines.append(f"**{brand} — Top Pick:**")
            lines.append(f"• {best['title']} — **{best['price_inr']}**{rating_s}")
            if len(products) > 1:
                lines.append(f"  *(+ {len(products) - 1} more option shown below)*")
            lines.append("")
        else:
            lines.append(f"**{brand}:** No results found — try a broader search term.")
            lines.append("")
        all_products.extend(products)

    lines.append("---")

    # Safe summary line — works for 1 or 2+ brands
    summary_parts = [f"**{c} {b}**" for b, c in zip(brands, counts)]
    lines.append(f"Showing {' and '.join(summary_parts)} option(s). "
                 f"Click any card to view and buy from the store.")
    lines.append("\n💡 **Buying tip:** Check ratings, warranty period, and after-sales "
                 "service availability in your city before deciding.")

    return '\n'.join(lines), all_products


# ── Pairing response ───────────────────────────────────────────────────────────
def _pairing_response(products: list, ents: dict, query: str) -> str:
    pairing_item  = ents.get('pairing_item') or 'your item'
    pairing_color = ents.get('pairing_color') or ''
    dept          = _dept(ents)
    n             = len(products)
    color_hint    = f"{pairing_color} " if pairing_color else ""

    if not products:
        return (
            f"## 👗 Pairing with your {color_hint}{pairing_item}\n\n"
            f"I couldn't find specific results right now. Try:\n"
            f"- *\"Show me {dept} to pair with {pairing_color} {pairing_item}\"*\n"
            f"- *\"Men's jeans under ₹1,500\"* for a direct search instead."
        )

    text = (
        f"## 👗 {dept.title()} to pair with your {color_hint}{pairing_item}\n\n"
        f"Found **{n} option{'s' if n != 1 else ''}** that go well with "
        f"a {color_hint}{pairing_item}. All prices in ₹.\n\n"
    )

    style_tips = {
        'jeans':    "Dark jeans pair best with lighter tops; light jeans work with bold or graphic tees.",
        't-shirt':  "Solid tees pair well with patterned bottoms; graphic tees work better with plain ones.",
        'kurta':    "Cotton kurtas pair nicely with churidars or jeans for a smart-casual look.",
        'saree':    "Choose a blouse that complements the saree border for a coordinated look.",
        'dress':    "A denim jacket or blazer over a dress works for both casual and smart occasions.",
        'hoodie':   "Slim-fit jeans or chinos keep the look balanced with a bulky hoodie.",
        'sneakers': "White sneakers are the most versatile — they work with almost any outfit.",
    }
    tip = style_tips.get(pairing_item, "Choose neutral or complementary tones for a put-together look.")
    text += f"💡 **Style tip:** {tip}"

    return text


# ── Single best response ───────────────────────────────────────────────────────
def _single_best_response(products: list, ents: dict, query: str) -> str:
    dept    = _dept(ents)
    price   = _price_s(ents)
    brands  = ents.get('brands', [])
    brand_s = f" from {brands[0]}" if brands else ""

    if not products:
        return (
            f"I couldn't find a top pick for **{dept}**{price}{brand_s} right now.\n\n"
            f"Try:\n"
            f"- Removing the budget filter\n"
            f"- Using a broader category — e.g. *\"best phone under ₹20,000\"*"
        )

    best = products[0]
    rating_s = f" | ⭐ {best['rating']}" if best.get('rating') else ""

    return (
        f"## 🏆 Best Pick: {_clean_heading(dept.title(), price, brand_s)}\n\n"
        f"Based on ratings and reviews, here's my **top recommendation**:\n\n"
        f"**{best['title']}**\n"
        f"Price: **{best['price_inr']}**{rating_s}\n\n"
        f"💡 Click the card below to view full details and buy from the store."
    )


# ── Listing response ───────────────────────────────────────────────────────────
def _listing_response(products: list, ents: dict, intent: str) -> str:
    dept    = _dept(ents)
    price   = _price_s(ents)
    color   = _color_s(ents)
    gender  = _gender_s(ents)
    brands  = ents.get('brands', [])
    n       = len(products)
    brand_s = f"by {brands[0]}" if brands else ""
    color_s = f"in {color}" if color else ""

    icons = {
        'price_filter':     '💰',
        'best_in_category': '🏆',
        'recommendation':   '🎯',
        'outfit':           '👗',
        'tech_spec':        '⚙️',
        'product_search':   '🔍',
    }
    icon = icons.get(intent, '🔍')

    heading = _clean_heading(
        f"## {icon}",
        f"{n} Results:" if intent == 'product_search' else f"{n}",
        gender,
        dept.title(),
        brand_s,
        color_s,
        price,
    )

    if not products:
        return (
            f"{heading}\n\n"
            f"No products found matching your query. Try:\n"
            f"- Removing filters (budget, color, brand)\n"
            f"- Using a simpler query — e.g. *\"gaming laptop India\"*"
        )

    tips = {
        'price_filter':     "💡 Prices may change daily — click any card for the latest price.",
        'best_in_category': "💡 Sort by *Customer Ratings* on Flipkart for the most trusted picks.",
        'recommendation':   "💡 Look for *Flipkart Assured* or *Amazon Prime* for faster delivery.",
        'outfit':           "💡 Mix one bold piece with neutral tones for an effortless look.",
        'tech_spec':        "💡 For gaming: prioritise GPU (RTX 4060+), 16GB RAM, 144Hz display.",
        'product_search':   "💡 Click any card to view details and buy from the store.",
    }

    tip = tips.get(intent, "💡 Click any card to view and buy.")
    return f"{heading}\n\nAll prices in ₹ (Indian Rupees). {tip}"


# ── Public API ─────────────────────────────────────────────────────────────────
def build_response(
    intent:      str,
    ents:        dict,
    query:       str,
    products:    list,
    brands_data: dict | None = None,
) -> tuple[str, list]:
    """
    Returns (text_answer, product_card_list).
    product_card_list is what gets rendered as cards in the UI.
    """

    # Info only — no product cards
    if intent == 'info_only':
        return _info_response(query, ents), []

    # Comparison
    if intent == 'comparison' and brands_data:
        return _comparison_response(brands_data, ents, query)

    # Single best
    if intent == 'single_best':
        return _single_best_response(products, ents, query), products[:1]

    # Fashion pairing
    if intent == 'pairing':
        return _pairing_response(products, ents, query), products

    # All other listing intents
    return _listing_response(products, ents, intent), products
