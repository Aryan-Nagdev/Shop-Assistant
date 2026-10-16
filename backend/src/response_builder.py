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
import re, sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.product_deduplicator import deduplicate_products

# ── LLM insight generator (reuses Groq client from llm_reason) ────────────────
def _llm_insight(prompt: str, max_tokens: int = 300) -> str:
    """Call Groq to generate a natural language insight. Returns empty str on failure."""
    try:
        from groq import Groq
        import config
        key = config.get_groq_api_key()
        if not key:
            return ""
        client = Groq(api_key=key)
        resp = client.chat.completions.create(
            model=config.GROQ_MODELS[0],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=max_tokens,
            timeout=5.0,
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


def _strip_markdown_bold(text: str) -> str:
    """Remove unwanted markdown ** asterisks everywhere from user-facing text."""
    if not text:
        return text
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    return cleaned.replace('**', '')


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
                    f"How to {topic_raw.title()}\n\n"
                    f"{tip}\n\n"
                    f"💡 Want to buy {dept}? Just ask me to find or recommend one — "
                    f"I'll pull live ₹ prices from Indian stores like Flipkart and Amazon.in."
                )

        # Generic how-to
        return (
            f"How to {topic_raw.title()}\n\n"
            f"Here are the key steps for {topic_raw}:\n"
            f"- Research the options available in India\n"
            f"- Compare brands by ratings and reviews\n"
            f"- Check warranty and after-sales support\n"
            f"- Buy from trusted stores: Flipkart, Amazon.in, Croma\n\n"
            f"💡 Want me to find or recommend {dept}? Just ask!"
        )

    # What is / explain
    if re.search(r'\bwhat is\b|\bwhat are\b|\bexplain\b|\bmeaning of\b', q):
        topic = re.sub(r'\bwhat (?:is|are)\b|\bexplain\b|\bmeaning of\b', '', q).strip()
        return (
            f"{topic.title()} is a popular product category in {dept}.\n\n"
            f"To get detailed specs and live ₹ prices, ask me to:\n"
            f"- 🔍 \"Find {topic} under ₹X\"\n"
            f"- ⚖️ \"Compare [Brand A] vs [Brand B] {topic}\"\n"
            f"- 🥇 \"Suggest 1 best {topic}\"\n\n"
            f"I'll fetch real listings from Flipkart, Amazon.in and more."
        )

    # Difference without brands
    if re.search(r'\bdifference\b', q) and not ents.get('brands'):
        return (
            "I can compare specific brands for you! Try:\n"
            "- \"Compare Dell vs HP laptop\"\n"
            "- \"Realme vs Vivo phone for gaming\"\n"
            "- \"Nike vs Adidas running shoes\"\n\n"
            "I'll show you side-by-side options with live ₹ prices."
        )

    return (
        "That's a great question! For specific product help, ask me to find, "
        "recommend, or compare — I'll pull live Indian store results with ₹ prices.\n\n"
        f"Try: \"Best {dept} under ₹10,000\" or \"Top {dept} in India\""
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

    # Fast comparison copy — skip Groq so product fetch is not blocked afterwards
    insight = ""
    if len(brands) >= 2 and brand_summaries:
        names = []
        for brand in brands[:2]:
            plist = brands_data.get(brand) or []
            if plist:
                names.append(f"{plist[0].get('title')} ({plist[0].get('price_inr', '')})")
        if names:
            insight = "Comparing the shown options, " + " vs ".join(names) + "."
        print(f"[ResponseBuilder] insight generated ({len(insight)} chars)")

    # ── Build clean response — no clutter ────────────────────────────────────
    result_lines = []

    if insight:
        result_lines.append(insight)
    else:
        if language == 'hi':
            comp_intros_hi = [
                f"यहाँ आपके द्वारा चुने गए {dept} ब्रांड्स की तुलना दी गई है:",
                f"आपके लिए शीर्ष {dept} ब्रांड्स का तुलनात्मक विवरण:",
                f"यहाँ इन {dept} विकल्पों की आमने-सामने तुलना दी गई है:",
            ]
            result_lines.append(random.choice(comp_intros_hi))
        else:
            comp_intros_en = [
                f"Here is a side-by-side comparison of the top {dept} brands you requested:",
                f"I've put together a head-to-head comparison of these {dept} options to help you decide:",
                f"Comparing the key options for {dept} across the requested brands:",
                f"Here is how these top {dept} picks stack up against each other:",
                f"Take a look at this brand-by-brand breakdown for your {dept} search:",
            ]
            result_lines.append(random.choice(comp_intros_en))

    return '\n'.join(result_lines), deduplicate_products(all_products)



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

    pairing_intros_en = [
        f"Here are top matching {dept} options curated to pair beautifully with your {color_hint}{pairing_item}:\n\n",
        f"Check out these stylish {dept} pieces that complement your {color_hint}{pairing_item} wonderfully:\n\n",
        f"I've selected these versatile {dept} picks to go perfectly with your {color_hint}{pairing_item}:\n\n",
        f"Here are some great coordinating {dept} options to complete your look with the {color_hint}{pairing_item}:\n\n",
    ]
    text = random.choice(pairing_intros_en)

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
    text += f"💡 Style tip: {tip}"

    return text


# ── Single best response ───────────────────────────────────────────────────────
def _single_best_response(products: list, ents: dict, query: str, language: str = 'en') -> str:
    dept    = _dept(ents)
    price   = _price_s(ents)
    brands  = ents.get('brands', [])
    brand_s = f" from {brands[0]}" if brands else ""
    wants_lowest = bool(ents.get('wants_lowest_price')) or bool(re.search(r'\b(?:cheapest|lowest\s*price|most\s*affordable|least\s*expensive|sasta|saste|kam\s*daam)\b', query, re.I))

    if not products:
        if language == 'hi':
            return f"मुझे अभी {dept}{price}{brand_s} के लिए सही विकल्प नहीं मिला। कृपया बजट या फ़िल्टर बदलकर दोबारा प्रयास करें।"
        return (
            f"I couldn't find a top pick for {dept}{price}{brand_s} right now.\n\n"
            f"Try:\n"
            f"- Removing the budget filter\n"
            f"- Using a broader category — e.g. \"best phone under ₹20,000\""
        )

    # If user wants the cheapest, sort to guarantee lowest priced
    if wants_lowest:
        priced_items = [p for p in products if (p.get('price_num') or 0) > 0]
        if priced_items:
            best = min(priced_items, key=lambda p: p.get('price_num') or 999999)
        else:
            best = products[0]
    else:
        best = products[0]

    rating_s = f" | ⭐ {best['rating']}" if best.get('rating') else ""

    if wants_lowest:
        templates_lowest_hi = [
            f"सबसे सस्ता उपलब्ध विकल्प {best['title']} है, जिसकी कीमत {best['price_inr']}{rating_s} है।",
            f"किफायती खरीदारी के लिए, {best['title']} सबसे कम कीमत पर {best['price_inr']}{rating_s} में उपलब्ध है।",
        ]
        templates_lowest_en = [
            f"The cheapest available option is {best['title']} priced at {best['price_inr']}{rating_s}.",
            f"For the most budget-friendly pick, {best['title']} comes in lowest at {best['price_inr']}{rating_s}.",
            f"If maximum savings is your goal, {best['title']} is the lowest-priced match at {best['price_inr']}{rating_s}.",
            f"The most affordable choice right now is {best['title']} at {best['price_inr']}{rating_s}.",
        ]
        if language == 'hi':
            return random.choice(templates_lowest_hi)
        elif language == 'hinglish':
            return f"Sabse sasta available option {best['title']} hai jo {best['price_inr']}{rating_s} mein available hai."
        return random.choice(templates_lowest_en)

    templates_single_hi = [
        f"आपके लिए मेरी शीर्ष सिफारिश {best['title']} है, जिसकी कीमत {best['price_inr']}{rating_s} है।",
        f"आपके अनुरोध के अनुसार {best['title']} ({best['price_inr']}{rating_s}) सबसे उत्कृष्ट विकल्प है।",
    ]
    templates_single_en = [
        f"My top recommendation for you is the {best['title']} priced at {best['price_inr']}{rating_s}.",
        f"The standout choice for your request is {best['title']} at {best['price_inr']}{rating_s}—it offers the best overall balance of quality and price.",
        f"If you're looking for the single best pick, go with {best['title']} ({best['price_inr']}{rating_s}).",
        f"After analyzing the options, {best['title']} at {best['price_inr']}{rating_s} clearly emerges as the top selection for your needs.",
        f"I'd strongly suggest {best['title']} ({best['price_inr']}{rating_s}) as your #1 pick in this category.",
        f"Your best bet is {best['title']} at {best['price_inr']}{rating_s}, offering top-tier performance in this segment.",
    ]
    if language == 'hi':
        return random.choice(templates_single_hi)
    elif language == 'hinglish':
        return f"Aapke liye meri top recommendation {best['title']} hai jo {best['price_inr']}{rating_s} mein available hai."
    return random.choice(templates_single_en)


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
    wants_lowest = bool(ents.get('wants_lowest_price')) or bool(re.search(r'\b(?:cheapest|lowest\s*price|most\s*affordable|least\s*expensive|sasta|saste|kam\s*daam)\b', query, re.I))
    max_price = ents.get('max_price')

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
            return "मुझे आपके द्वारा मांगे गए सटीक उत्पाद नहीं मिले। कृपया बजट या फ़िल्टर थोड़ा बदलकर दोबारा प्रयास करें।"

        # Build a context-aware message based on what was understood
        understood_parts = []
        if brands:
            understood_parts.append(f"brand: {brands[0]}")
        if ents.get('gender'):
            understood_parts.append(f"gender: {ents['gender']}'s")
        if dept and dept != 'products':
            understood_parts.append(f"category: {dept}")
        if max_price:
            understood_parts.append(f"budget: under ₹{max_price:,}")

        understood_str = (
            f" (understood: {', '.join(understood_parts)})" if understood_parts else ""
        )

        # Suggest a broader retry query
        retry_hint = dept if dept and dept != 'products' else 'clothing'
        brand_hint = f"{brands[0]} " if brands else ""

        return (
            f"I couldn't find matching products right now{understood_str}.\n\n"
            f"Try:\n"
            f"- Broader search: \"{brand_hint}{retry_hint}\" without extra filters\n"
            f"- Or rephrase: e.g. \"{brand_hint}men's {retry_hint}\" or \"{brand_hint}best {retry_hint}\""
        )


    # ── Check if requested budget is exceeded by all products or budget_relaxed alternative ───
    budget_alts = [p for p in products if p.get('alternative_type') == 'budget_relaxed']
    priced_prods = [p for p in products if (p.get('price_num') or 0) > 0]
    all_over_budget = max_price and priced_prods and all((p.get('price_num') or 0) > max_price for p in priced_prods)

    if budget_alts or all_over_budget:
        best_b = budget_alts[0] if budget_alts else min(priced_prods, key=lambda p: p.get('price_num') or 999999)
        orig_b = int(best_b.get('original_budget') or max_price or 0)
        lowest_p = int(best_b.get('lowest_matching_price') or best_b.get('price_num') or 0)
        diff = int(best_b.get('budget_diff') or (lowest_p - orig_b if lowest_p > orig_b else 0))

        if language == 'hi':
            if orig_b and lowest_p and diff > 0:
                return f"₹{orig_b:,} के तहत कोई सटीक उत्पाद नहीं मिला। सबसे कम कीमत वाला मेल खाने वाला विकल्प ₹{lowest_p:,} है, इसलिए आपको अपना बजट ₹{diff:,} बढ़ाना पड़ सकता है।"
            else:
                return f"मुझे आपके बजट के तहत कोई सटीक उत्पाद नहीं मिला। निकटतम उत्पाद {best_b.get('price_inr', '')} से शुरू होता है।"
        else:
            if orig_b and lowest_p and diff > 0:
                return (
                    f"No exact match was found under ₹{orig_b:,}. "
                    f"The lowest-priced matching option I found is ₹{lowest_p:,}, "
                    f"so you may need to increase your budget by ₹{diff:,}."
                )
            elif orig_b and lowest_p:
                return (
                    f"I couldn't find an exact match under ₹{orig_b:,}. "
                    f"The closest matching product starts at ₹{lowest_p:,}. "
                    f"You may need to increase your budget to ₹{lowest_p:,}."
                )

    # ── Handle Other Smart Alternative Responses (Phase 3 Spec Relaxation) ────
    if any(p.get('is_alternative') for p in products):
        spec_alts = [p for p in products if p.get('alternative_type') == 'spec_relaxed']
        if spec_alts:
            best_s = spec_alts[0]
            explanation = best_s.get('alternative_explanation') or best_s.get('alternative_diff', '')
            return f"Here is a recommended in-budget pick: {best_s['title']} at {best_s['price_inr']} ({explanation})"

    # If lowest price is requested, identify the lowest priced and next affordable options
    if wants_lowest and products:
        priced_prods = [p for p in products if (p.get('price_num') or 0) > 0]
        if priced_prods:
            priced_prods.sort(key=lambda p: p.get('price_num') or 999999)
            cheapest = priced_prods[0]
            extra_c = f" Another affordable option is {priced_prods[1]['title']} at {priced_prods[1].get('price_inr', '')}." if len(priced_prods) > 1 else ""
            if language == 'hi':
                return f"सबसे सस्ता {dept} विकल्प {cheapest['title']} है जो {cheapest.get('price_inr', '')} पर उपलब्ध है।{extra_c}"
            return f"The cheapest {dept} available is {cheapest['title']} priced at {cheapest.get('price_inr', '')}.{extra_c}"

    # Dynamic conversational listing copy
    return _generate_dynamic_summary(products, ents, query=query, language=language)


def _generate_dynamic_summary(products: list, ents: dict, query: str = "", language: str = "en") -> str:
    """
    Generate dynamic, fresh conversational response copy every time, like ChatGPT.
    Tries Groq LLM with temperature=0.8 for creative natural phrasing, and falls back to
    a diverse collection of 10+ randomized conversational phrasing angles.
    """
    if not products:
        return ""

    dept = _dept(ents)
    best = products[0]
    best_title = best.get('title', 'Top Pick')
    best_price = best.get('price_inr', '')
    second = products[1] if len(products) > 1 else None
    sec_title = second.get('title', '') if second else ''
    sec_price = second.get('price_inr', '') if second else ''

    # 1. Try Groq for dynamic, creative AI phrasing
    try:
        from groq import Groq
        key = config.get_groq_api_key()
        if key:
            client = Groq(api_key=key)
            prods_summary = "; ".join(f"{p.get('title')} ({p.get('price_inr', '')})" for p in products[:3])
            prompt = (
                f"You are a friendly, expert India e-commerce shopping AI assistant.\n"
                f"User asked: \"{query}\"\n"
                f"Category: {dept}\n"
                f"Top products found: {prods_summary}\n\n"
                f"Write a fresh, natural, engaging 1 to 2 sentence conversational intro for the user.\n"
                f"Highlight key value, performance, or suitability for their request.\n"
                f"Every time this runs, use a DIFFERENT conversational opening, tone, and angle so repeated queries get unique, human-like answers like ChatGPT.\n"
                f"Do NOT use markdown bold asterisks (**). Output ONLY the sentences, no quotes."
            )
            resp = client.chat.completions.create(
                model=config.GROQ_MODELS[0],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=140,
                timeout=3.5,
            )
            content = resp.choices[0].message.content.strip()
            if content and len(content) > 15:
                return _strip_markdown_bold(content)
    except Exception as e:
        pass

    # 2. Rich, randomized conversational templates (no repetition)
    extra_variants = [
        f" Another standout alternative is {sec_title} at {sec_price}." if second else "",
        f" A strong next option is {sec_title} priced at {sec_price}." if second else "",
        f" You might also want to consider {sec_title} at {sec_price}." if second else "",
        f" Followed closely by {sec_title} ({sec_price}), which is also highly rated." if second else "",
        f" For great variety, {sec_title} at {sec_price} is another top contender." if second else "",
    ]
    extra_text = random.choice(extra_variants)

    if language == 'hi':
        templates_hi = [
            f"आपके अनुरोध के अनुसार शीर्ष विकल्प मिले हैं। सबसे आगे {best_title} है जो {best_price} पर उपलब्ध है।",
            f"यहाँ आपके लिए बेहतरीन विकल्प हैं! {best_title} ({best_price}) अपनी गुणवत्ता और प्रदर्शन के लिए शानदार है।",
            f"आपके मापदंडों के अनुसार मैंने सबसे अच्छे विकल्प चुने हैं। {best_title} {best_price} में एक बहुत बढ़िया विकल्प है।",
            f"यहाँ लाइव उत्पाद उपलब्ध हैं। {best_title} की कीमत {best_price} है और यह एक अत्यधिक अनुशंसित विकल्प है।",
        ]
        return random.choice(templates_hi)

    if language == 'hinglish':
        templates_hinglish = [
            f"Aapke request ke mutabiq best options mil gaye hain! Sabse aage {best_title} hai jo {best_price} par available hai.{extra_text}",
            f"Ye rahe aapke search ke top matches. {best_title} ({best_price}) ek kaafi solid choice hai.{extra_text}",
            f"Maine aapke criteria ke hisaab se best picks nikale hain. {best_title} at {best_price} stands out right now.{extra_text}",
            f"Here are live matches! {best_title} is priced at {best_price} and is highly recommended.{extra_text}",
        ]
        return random.choice(templates_hinglish)

    templates_en = [
        f"I've rounded up some great options for your search! Leading the lineup is {best_title} at {best_price}.{extra_text}",
        f"Here are top-rated matches tailored to your request. {best_title} stands out at {best_price} for its solid overall balance of features and value.{extra_text}",
        f"Based on what you're looking for, {best_title} ({best_price}) is a standout choice in this category.{extra_text}",
        f"Take a look at these recommended options. {best_title} is currently one of the most compelling picks in this range at {best_price}.{extra_text}",
        f"Here is a curated selection matching your requirements. {best_title} at {best_price} delivers excellent performance and build.{extra_text}",
        f"I found these top live matches for you! A leading contender is {best_title} priced at {best_price}.{extra_text}",
        f"Check out these high-rated picks! {best_title} ({best_price}) is an impressive option that fits your criteria nicely.{extra_text}",
        f"Here are the best current options for your query. {best_title} at {best_price} offers outstanding bang for your buck.{extra_text}",
        f"Explore these top recommendations! {best_title} ({best_price}) is leading the pack with stellar feedback.{extra_text}",
        f"Here's what I found for you! {best_title} is priced at {best_price} and offers a great combination of features and reliability.{extra_text}",
    ]
    return random.choice(templates_en)


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
            lines.append(f"{label}")
            lines.append(f"• {best['title']} — {best['price_inr']}{rating_s}")
            if len(prods) > 1:
                lines.append(f"  (+ {len(prods)-1} more below)")
            all_cards.extend(prods[:2])
        else:
            lines.append(f"{label} — No results found.")
        lines.append("")

    fashion_depts = {'Jeans', 'T-Shirts', 'Footwear', 'Shirts', 'Dresses', 'Jackets', 'Ethnic Wear', 'Clothing', 'Office Wear'}
    if any(label in fashion_depts for label in products_by_label.keys()):
        lines.append("Mix neutral tones for one piece and let the other be the statement item.")
    return _strip_markdown_bold('\n'.join(lines)), deduplicate_products(all_cards)


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
    if products:
        products = deduplicate_products(products)

    # ── Information (no product cards) ────────────────────────────────────────
    if intent == 'information':
        text = _information_response_llm(llm_explanation, query)
        return _strip_markdown_bold(text), []

    # ── Info only (legacy fallback — kept for backward compat) ────────────────
    if intent == 'info_only':
        text = _info_response(query, ents)
        count = ents.get('count')
        if count and isinstance(count, int):
            products = products[:count]
        return _strip_markdown_bold(text), products

    # ── Comparison ────────────────────────────────────────────────────────────
    if intent == 'comparison':
        if brands_data:
            # search_required=True path: real product data available
            text, prods = _comparison_response(brands_data, ents, query, language=language)
            return _strip_markdown_bold(text), prods
        else:
            # search_required=False path: text-only comparison
            text = _comparison_text_response(llm_explanation, ents, query)
            return _strip_markdown_bold(text), []

    # ── Multi-item (jeans + t-shirt + sneakers) ───────────────────────────────
    if intent == 'multi_item' and brands_data:
        text, prods = _multi_item_response(brands_data, ents)
        return _strip_markdown_bold(text), prods

    # ── Single best ───────────────────────────────────────────────────────────
    if intent == 'single_best':
        text = _single_best_response(products, ents, query, language=language)
        return _strip_markdown_bold(text), products[:1]

    # ── Fashion pairing ───────────────────────────────────────────────────────
    if intent == 'pairing':
        text = _pairing_response(products, ents, query)
        return _strip_markdown_bold(text), products

    # ── Respect explicit count for listing intents ────────────────────────────
    count = ents.get('count')
    if count and isinstance(count, int) and count > 1:
        products = products[:count]

    # ── All other listing intents ─────────────────────────────────────────────
    text = _listing_response(products, ents, intent, query=query, language=language)
    return _strip_markdown_bold(text), products