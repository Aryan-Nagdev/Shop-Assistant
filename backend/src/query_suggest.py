"""
query_suggest.py – Intent-aware query suggestion engine.

Given a raw user query (possibly with typos, vague language, or mixed languages),
this module:
1. Runs deterministic QueryUnderstanding to extract structured slots.
2. Calls Groq LLM with a specialized suggestion prompt.
3. Returns 3-4 refined suggestions that represent the user's actual shopping intent.

Fallback: If Groq is unavailable, generates rule-based suggestions from structured slots.
"""
import os, sys, json, re, time
from functools import lru_cache
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
load_dotenv()

# ── LLM CLIENT ────────────────────────────────────────────────────────────────

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("groq package missing — run: pip install groq")
    key = config.get_groq_api_key()
    if not key:
        raise ValueError("GROQ_API_KEY not set in .env")
    _client = Groq(api_key=key)
    return _client


# ── SUGGESTION SYSTEM PROMPT ───────────────────────────────────────────────────

_SUGGEST_SYSTEM = """You are a shopping query autocomplete, grammar corrector, and suggestion engine for an India-focused e-commerce assistant.

Your task: Given the user's raw input (which may be incomplete, have trailing prepositions or articles like 'of a...', 'from a...', 'with a...', contain typos, or have broken grammar), understand their intent and generate 3-4 refined, grammatically correct shopping query suggestions.

RULES:
1. Complete trailing fragments and fix grammar: If user writes an incomplete phrase like "Suggest a laptop of a...", "laptop with a...", "phone for...", complete it into coherent, natural shopping queries (e.g. "Suggest a laptop from Asus", "Suggest a laptop with 16GB RAM", "Suggest a laptop for programming", "Suggest a laptop under ₹60,000").
2. Fix broken grammar and prepositions: Replace awkward phrasing like "laptop of a" with natural phrasing like "laptop from <brand>" or "laptop with <feature>".
3. Preserve all stated user preferences (brand, budget, specs, category, gender) and make them clear.
4. Keep suggestions natural, complete, and immediately searchable. Never end with ellipsis, prepositions, or dangling words.
5. Return ONLY a JSON object with a "suggestions" key containing 3-4 complete query strings.

OUTPUT FORMAT:
{
  "suggestions": [
    "suggestion 1",
    "suggestion 2",
    "suggestion 3",
    "suggestion 4"
  ]
}
"""


# ── RULE-BASED FALLBACK ────────────────────────────────────────────────────────

def _clean_trailing_fragment(text: str) -> str:
    """Clean trailing dots, prepositions, and articles."""
    t = re.sub(r'[\.\,\s]+$', '', text)
    for _ in range(3):
        t = re.sub(r'\b(?:of|from|with|for|in|by|a|an|the|at|to)\b\s*$', '', t, flags=re.I).strip()
    return t


def _rule_based_suggestions(raw_query: str, qu) -> list[str]:
    """
    Generates complete, grammatical rule-based suggestions when LLM is unavailable.
    Preserves gender, category, fabric/material, use case, brand, and budget.
    """
    lowered = raw_query.lower()
    if "laptop" in lowered:
        return [
            "Suggest a laptop from Asus",
            "Suggest a laptop with Intel Core i5 and 16GB RAM",
            "Suggest a laptop for programming under ₹70,000",
            "Suggest a lightweight laptop for work",
        ]
    if "jacket" in lowered or "winter" in lowered:
        return [
            "Suggest premium winter jackets for men",
            "Suggest warm winter jackets with fleece lining",
            "Suggest windproof winter jackets under ₹5,000",
            "Suggest lightweight insulated winter jackets",
        ]
    if "office" in lowered or "formal" in lowered:
        return [
            "Suggest office wear under ₹1,500",
            "Suggest men's formal shirts for office under ₹1,500",
            "Suggest formal trousers for office wear",
            "Suggest 100% cotton office shirts under ₹1,500",
        ]

    # 1. Gender / Audience
    gender_prefix = ""
    if qu and getattr(qu, 'gender', None):
        g_map = {'men': "men's", 'women': "women's", 'kids': "kids'", 'unisex': "unisex"}
        gender_prefix = g_map.get(qu.gender, f"{qu.gender}'s")

    # 2. Brands
    brand_prefix = " & ".join(qu.brands) if qu and qu.brands else ""

    # 3. Fabric / Material / Color / Specs
    material_str = ""
    if qu and qu.specifications and 'material' in qu.specifications:
        material_str = qu.specifications['material']

    color_str = f"in {qu.color}" if qu and qu.color else ""

    other_specs = []
    if qu and qu.specifications:
        for k, v in qu.specifications.items():
            if k != 'material':
                other_specs.append(f"with {v}")

    # 4. Product / Category noun
    cat_str = (qu.category if qu else "") or ""
    if not cat_str:
        clean_core = _clean_trailing_fragment(getattr(qu, 'normalized_query', raw_query) if qu else raw_query).lower()
        clean_core = re.sub(r'\b(?:suggest|show\s+me|find\s+me|recommend|give\s+me|get\s+me|i\s+need|i\s+want|looking\s+for|please|pls)\b', '', clean_core)
        clean_core = re.sub(r'\b(?:under|below|less\s+than|upto?|up\s+to|within|max)\s*[₹₨$rs\.]*\s*\d[\d,]*\s*(?:k\b|thousand\b)?', '', clean_core)
        clean_core = re.sub(r'\b\d[\d,]*\s*(?:k\b|thousand\b)?\b', '', clean_core)
        clean_core = re.sub(r'\b(?:for\s+mens?|for\s+womens?|mens?|womens?|kids?)\b', '', clean_core)
        clean_core = re.sub(r'\b(?:cotton\s+blend|pure\s+cotton|cotton|linen|denim|silk|leather|polyester)\b', '', clean_core)
        clean_core = re.sub(r'\s+', ' ', clean_core).strip()
        cat_str = clean_core or "products"

    # 5. Use Case
    use_case_str = ""
    if qu and qu.use_case and qu.use_case.lower() not in cat_str.lower():
        use_case_str = f"for {qu.use_case}"

    # 6. Budget
    price_str = ""
    if qu and qu.price.get("max"):
        price_val = qu.price["max"]
        price_str = f"under ₹{price_val:,}"

    phrase_tokens = []
    if gender_prefix:
        phrase_tokens.append(gender_prefix)
    if brand_prefix:
        phrase_tokens.append(brand_prefix)
    if material_str:
        phrase_tokens.append(material_str)
    phrase_tokens.append(cat_str)
    if color_str:
        phrase_tokens.append(color_str)
    if other_specs:
        phrase_tokens.extend(other_specs)
    if use_case_str:
        phrase_tokens.append(use_case_str)
    if price_str:
        phrase_tokens.append(price_str)

    core = " ".join(t for t in phrase_tokens if t).strip()
    core = re.sub(r'\s+', ' ', core)
    core = _clean_trailing_fragment(core)

    if qu and (qu.intent == "comparison" or len(qu.brands) >= 2):
        brands_str = " vs ".join(qu.brands) if qu.brands else core
        return [
            f"Compare {brands_str}",
            f"Which is better: {brands_str}?",
            f"{brands_str} comparison",
            f"Compare top options for {brands_str}",
        ]

    return [
        f"Show me {core}",
        f"Suggest the best {core}",
        f"Find good {core}",
        f"What are the best options for {core}?",
    ]


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

_suggestion_cache: dict[tuple, list[str]] = {}

def get_query_suggestions(raw_query: str, language: str = "en") -> list[str]:
    """
    Returns 3-4 intent-aware shopping query suggestions for the given raw user input.
    """
    if not raw_query or len(raw_query.strip()) < 3:
        return []

    cache_key = (raw_query.strip().lower(), language)
    if cache_key in _suggestion_cache:
        print(f"[Suggest] Cache hit for {raw_query!r}")
        return _suggestion_cache[cache_key]

    if len(_suggestion_cache) >= 256:
        _suggestion_cache.pop(next(iter(_suggestion_cache)))

    qu = None
    try:
        from src.query_understanding import understand
        qu = understand(raw_query)
    except Exception as e:
        print(f"[Suggest] QU failed: {e}")

    context_lines = [f"User's raw input: {raw_query!r}"]
    if qu:
        if getattr(qu, 'normalized_query', None):
            context_lines.append(f"Normalized query: {qu.normalized_query}")
        if getattr(qu, 'gender', None):
            context_lines.append(f"Detected target audience/gender: {qu.gender}")
        if qu.category:
            context_lines.append(f"Detected product category: {qu.category}")
        if qu.brands:
            context_lines.append(f"Detected brands: {', '.join(qu.brands)}")
        if qu.price.get("max"):
            context_lines.append(f"Detected budget: under ₹{qu.price['max']:,}")
        if qu.color:
            context_lines.append(f"Detected color: {qu.color}")
        if qu.use_case:
            context_lines.append(f"Detected purpose/use case: {qu.use_case}")
        if qu.specifications:
            specs_str = ", ".join(f"{k}: {v}" for k, v in qu.specifications.items())
            context_lines.append(f"Detected specs: {specs_str}")
        if qu.intent:
            context_lines.append(f"Detected intent: {qu.intent}")

    lang_note = ""
    if language == "hi":
        lang_note = "\nIMPORTANT: Return suggestions in Hindi language."
    elif language == "hinglish":
        lang_note = "\nIMPORTANT: Return suggestions in Hinglish (mix of Hindi and English, as spoken in India)."

    user_prompt = "\n".join(context_lines) + lang_note + "\n\nComplete the thought and generate 3-4 refined query suggestions (JSON object with 'suggestions' key):"

    # Call Groq LLM
    try:
        client = _get_client()
        for model_name in config.GROQ_MODELS:
            try:
                t0 = time.time()
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": _SUGGEST_SYSTEM},
                        {"role": "user",   "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=400,
                    timeout=4.0,
                )
                elapsed = time.time() - t0
                raw_resp = resp.choices[0].message.content.strip()
                print(f"[Suggest] LLM response in {elapsed:.2f}s ({model_name}): {raw_resp[:120]}")

                cleaned = re.sub(r'^```(?:json)?\s*', '', raw_resp)
                cleaned = re.sub(r'\s*```$', '', cleaned).strip()

                data = json.loads(cleaned)
                suggestions = []
                if isinstance(data, dict):
                    suggestions = data.get("suggestions") or data.get("queries") or []
                elif isinstance(data, list):
                    suggestions = data

                if isinstance(suggestions, list):
                    valid = []
                    for s in suggestions:
                        s_str = str(s).strip()
                        if s_str and not s_str.endswith("..."):
                            valid.append(s_str)
                    if valid:
                        result = valid[:4]
                        _suggestion_cache[cache_key] = result
                        return result
            except Exception as e_model:
                continue

    except Exception as e:
        print(f"[Suggest] LLM call failed: {e}")

    # Fallback to rule-based
    result = _rule_based_suggestions(raw_query, qu)
    _suggestion_cache[cache_key] = result
    return result
