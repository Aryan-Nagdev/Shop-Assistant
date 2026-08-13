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
import re, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── LLM insight generator (reuses Groq client from llm_reason) ────────────────
def _llm_insight(prompt: str, max_tokens: int = 300) -> str:
    """Call Groq to generate a natural language insight. Returns empty str on failure."""
    try:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY", "").strip().strip("'\"")
        if not key:
            return ""
        client = Groq(api_key=key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ResponseBuilder] LLM insight failed: {e}")
        return ""


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
    return ents.get('dept') or ents.get('product_name') or 'products'


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


# ── Information response (no product cards) ────────────────────────────────────
def _information_response_llm(explanation: str, query: str) -> str:
    """
    For intent=information when search_required=False.
    Uses LLM explanation as primary answer with a soft nudge.
    """
    if explanation:
        nudge = "\n\n↪ *Want me to find or compare actual products? Just ask!*"
        return explanation + nudge
    # Fallback to generic info response
    ents: dict = {}
    return _info_response(query, ents)


# ── Comparison text response (no product cards) ────────────────────────────────
def _comparison_text_response(explanation: str, ents: dict, query: str) -> str:
    """
    For intent=comparison when search_required=False.
    Produces a clean text-only comparison without product cards.
    """
    if explanation:
        nudge = "\n\n↪ *Want me to find actual products with live ₹ prices? Just ask!*"
        return explanation + nudge
    # Fallback: generic comparison nudge
    brands = ents.get('brands', [])
    brand_s = " and ".join(brands[:2]) if brands else "both"
    dept = _dept(ents)
    return (
        f"Both {brand_s} have their strengths for {dept}. "
        f"The best choice depends on your specific needs, budget, and use case.\n\n"
        f"↪ *Want me to find actual products with live prices? Try: "
        f"\"Compare {brand_s} {dept} under ₹X\"*"
    )


# ── Comparison response ────────────────────────────────────────────────────────
def _comparison_response(
    brands_data: dict[str, list], ents: dict, query: str, language: str = 'en'
) -> tuple[str, list]:
    brands = list(brands_data.keys())
    dept   = _dept(ents)
    price  = _price_s(ents)

    if not brands:
        if language == 'hi':
            return ("तुलना के लिए कोई परिणाम नहीं मिले। कृपया दोनों ब्रांड स्पष्ट रूप से बताएं।", [])
        return (
            "Couldn't find results for the comparison. "
            "Try mentioning both brand names clearly, e.g. Realme vs Samsung phone.",
            []
        )

    all_products: list = []
    brand_summaries = []

    for brand, products in brands_data.items():
        all_products.extend(products)
        if products:
            items = []
            for p in products[:3]:
                title   = p.get('title', '')
                price_v = p.get('price_inr', '')
                rating  = p.get('rating', '')
                items.append(f"- {title} | {price_v}" + (f" | {rating}" if rating else ""))
            brand_summaries.append(f"{brand}:\n" + "\n".join(items))

    # ── LLM insight from real product data ───────────────────────────────────
    insight = ""
    if len(brands) >= 2 and brand_summaries:
        products_text = "\n\n".join(brand_summaries)
        lang_note = ""
        if language == 'hi':
            lang_note = "- Write the response in natural, clear Hindi (Devanagari script), keeping prices in ₹ and brand names in English/Hindi."
        elif language == 'hinglish':
            lang_note = "- Write the response in friendly, conversational Hinglish (Latin script)."

        insight_prompt = (
            f"You are a knowledgeable India e-commerce shopping assistant.\n"
            f"User asked: \"{query}\"\n\n"
            f"Actual products found (live Indian prices):\n\n"
            f"{products_text}\n\n"
            f"Write a SHORT, DIRECT comparison answer (3-5 sentences). Rules:\n"
            f"- Reference actual product names and prices from the data\n"
            f"- Directly answer what the user asked (camera/gaming/value/etc.)\n"
            f"- Give a clear winner recommendation with reason\n"
            f"- Conversational tone, no markdown, no bullet points\n"
            f"{lang_note}\n"
            f"- Do NOT say \"based on the data\" or \"I found\" — just answer directly"
        )
        insight = _llm_insight(insight_prompt, max_tokens=250)
        print(f"[ResponseBuilder] insight generated ({len(insight)} chars)")

    # ── Build clean response — no clutter ────────────────────────────────────
    result_lines = []

    if insight:
        result_lines.append(insight)
    else:
        if language == 'hi':
            result_lines.append(f"यहाँ आपके द्वारा चुने गए {dept} ब्रांड्स की तुलना दी गई है:")
        else:
            result_lines.append(f"Here is a side-by-side comparison of the top {dept} brands you requested:")

    return '\n'.join(result_lines), all_products



# ── Pairing response ───────────────────────────────────────────────────────────
def _pairing_response(products: list, ents: dict, query: str) -> str:
    pairing_item  = ents.get('pairing_item') or 'your item'
    pairing_color = ents.get('pairing_color') or ''
    dept          = _dept(ents)
    n             = len(products)
    color_hint    = f"{pairing_color} " if pairing_color else ""

    if not products:
        return (
            f"I couldn't find specific matching {dept} to pair with your {color_hint}{pairing_item} right now. "
            f"Try searching for broader outfit components."
        )

    text = (
        f"Here are top matching {dept} options curated to pair beautifully with your {color_hint}{pairing_item}:\n\n"
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
def _single_best_response(products: list, ents: dict, query: str, language: str = 'en') -> str:
    dept    = _dept(ents)
    price   = _price_s(ents)
    brands  = ents.get('brands', [])
    brand_s = f" from {brands[0]}" if brands else ""

    if not products:
        if language == 'hi':
            return f"मुझे अभी **{dept}**{price}{brand_s} के लिए सही विकल्प नहीं मिला। कृपया बजट या फ़िल्टर बदलकर दोबारा प्रयास करें।"
        return (
            f"I couldn't find a top pick for **{dept}**{price}{brand_s} right now.\n\n"
            f"Try:\n"
            f"- Removing the budget filter\n"
            f"- Using a broader category — e.g. *\"best phone under ₹20,000\"*"
        )

    best = products[0]
    rating_s = f" | ⭐ {best['rating']}" if best.get('rating') else ""

    if language == 'hi':
        return f"आपके लिए मेरी शीर्ष सिफारिश **{best['title']}** है, जिसकी कीमत **{best['price_inr']}**{rating_s} है।"
    elif language == 'hinglish':
        return f"Aapke liye meri top recommendation **{best['title']}** hai jo **{best['price_inr']}**{rating_s} mein available hai."
    return f"My top recommendation for you is the **{best['title']}** priced at **{best['price_inr']}**{rating_s}."


# ── Listing response ───────────────────────────────────────────────────────────
def _listing_response(products: list, ents: dict, intent: str, query: str = "", language: str = "en") -> str:
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

    if not products:
        if language == 'hi':
            return "आपके मापदंडों से मेल खाने वाला कोई उत्पाद नहीं मिला। कृपया बजट या फ़िल्टर थोड़ा बढ़ाकर खोजें।"
        return (
            "No suitable exact product found that meets all your criteria.\n\n"
            "Try:\n"
            "- Broadening your budget filter\n"
            "- Removing specific constraint filters (such as brand, color, or exact specs)"
        )

    # ── Handle Smart Alternative Responses (Phase 3) ──────────────────────────
    if any(p.get('is_alternative') for p in products):
        budget_alts = [p for p in products if p.get('alternative_type') == 'budget_relaxed']
        spec_alts = [p for p in products if p.get('alternative_type') == 'spec_relaxed']
        
        lines = []
        query_clean = query.strip()
        lines.append(f"I couldn't find an exact match for **\"{query_clean}\"** under your requested budget.")
        lines.append("")
        
        if budget_alts:
            best_b = budget_alts[0]
            lines.append(f"**Closest match:** **{best_b['price_inr']}** *({best_b.get('alternative_diff', '')})*")
            lines.append(f"• **{best_b['title']}**")
            lines.append(f"That's the lowest-priced option matching your requested specifications.")
            lines.append("")
            
        if spec_alts:
            best_s = spec_alts[0]
            lines.append(f"**In-budget alternative:** **{best_s['price_inr']}**")
            lines.append(f"• **{best_s['title']}**")
            lines.append(f"*{best_s.get('alternative_explanation', '')}*")
            lines.append("")

        return '\n'.join(lines).strip()

    # Generate LLM insight from real product data when a user query is present
    insight = ""
    if query and products:
        top_items = []
        for p in products[:4]:
            title   = p.get('title', '')
            price_v = p.get('price_inr', '')
            rating  = p.get('rating', '')
            top_items.append(f"- {title} | {price_v}" + (f" | ⭐{rating}" if rating else ""))
        products_text = "\n".join(top_items)

        lang_note = ""
        if language == 'hi':
            lang_note = "- Write the answer in natural Hindi (Devanagari script), keeping prices in ₹ format."
        elif language == 'hinglish':
            lang_note = "- Write the answer in friendly Hinglish (Latin script)."

        insight_prompt = (
            f"You are a helpful India e-commerce assistant.\n"
            f"User asked: \"{query}\"\n\n"
            f"Top products found (live Indian prices):\n{products_text}\n\n"
            f"Write 2-3 SHORT sentences that directly answer the user's query.\n"
            f"- Mention 1-2 specific product names and prices\n"
            f"- Give a concrete recommendation\n"
            f"- Conversational tone, ₹ for prices, no markdown, no bullet points\n"
            f"{lang_note}\n"
            f"- Do NOT start with \"Based on\" or \"I found\" — answer directly"
        )
        insight = _llm_insight(insight_prompt, max_tokens=180)

    if insight:
        result = insight
    else:
        if language == 'hi':
            result = "यहाँ आपके बजट और पसंद के अनुसार सबसे अच्छे विकल्प दिए गए हैं:"
        else:
            result = "Here are the top matches matching your specifications and budget:"
    return result


def _multi_item_response(products_by_label: dict, ents: dict) -> tuple[str, list]:
    """
    For queries like 'jeans + t-shirt + sneakers'.
    products_by_label: {dept_label: [products]}
    Returns grouped text + flat product list.
    """
    lines = []
    all_cards = []

    icons = {
        'Jeans': '👖', 'T-Shirts': '👕', 'Footwear': '👟', 'Shirts': '👔',
        'Dresses': '👗', 'Jackets': '🧥', 'Watches': '⌚', 'Bags': '🎒',
        'Mobile Phones': '📱', 'Laptops': '💻', 'Audio': '🎧',
    }

    for label, prods in products_by_label.items():
        icon = icons.get(label, '🔍')
        if prods:
            best = prods[0]
            rating_s = f" ⭐ {best['rating']}" if best.get('rating') else ''
            lines.append(f"**{label}**")
            lines.append(f"• {best['title']} — **{best['price_inr']}**{rating_s}")
            if len(prods) > 1:
                lines.append(f"  *(+ {len(prods)-1} more below)*")
            all_cards.extend(prods[:2])
        else:
            lines.append(f"**{label}** — No results found.")
        lines.append("")

    lines.append("Mix neutral tones for one piece and let the other be the statement item.")
    return '\n'.join(lines), all_cards


# ── Public API ─────────────────────────────────────────────────────────────────
def build_response(
    intent:          str,
    ents:            dict,
    query:           str,
    products:        list,
    brands_data:     dict | None = None,
    llm_explanation: str = '',
    language:        str = 'en',
) -> tuple[str, list]:
    """
    Returns (text_answer, product_card_list).
    product_card_list is what gets rendered as cards in the UI.

    llm_explanation: the raw explanation string from llm_reason().
                     Used for information and no-search comparison responses.
    language: 'en', 'hi', or 'hinglish'
    """

    # ── Information (no product cards) ────────────────────────────────────────
    if intent == 'information':
        text = _information_response_llm(llm_explanation, query)
        return text, []

    # ── Info only (legacy fallback — kept for backward compat) ────────────────
    if intent == 'info_only':
        text = _info_response(query, ents)
        count = ents.get('count')
        if count and isinstance(count, int):
            products = products[:count]
        return text, products

    # ── Comparison ────────────────────────────────────────────────────────────
    if intent == 'comparison':
        if brands_data:
            # search_required=True path: real product data available
            return _comparison_response(brands_data, ents, query, language=language)
        else:
            # search_required=False path: text-only comparison
            text = _comparison_text_response(llm_explanation, ents, query)
            return text, []

    # ── Multi-item (jeans + t-shirt + sneakers) ───────────────────────────────
    if intent == 'multi_item' and brands_data:
        return _multi_item_response(brands_data, ents)

    # ── Single best ───────────────────────────────────────────────────────────
    if intent == 'single_best':
        return _single_best_response(products, ents, query, language=language), products[:1]

    # ── Fashion pairing ───────────────────────────────────────────────────────
    if intent == 'pairing':
        return _pairing_response(products, ents, query), products

    # ── Respect explicit count for listing intents ────────────────────────────
    count = ents.get('count')
    if count and isinstance(count, int):
        products = products[:count]

    # ── All other listing intents ─────────────────────────────────────────────
    return _listing_response(products, ents, intent, query=query, language=language), products