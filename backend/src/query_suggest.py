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
    key = (getattr(config, 'GROQ_API_KEY', None) or os.getenv("GROQ_API_KEY", "")).strip().strip("'\"")
    if not key:
        raise ValueError("GROQ_API_KEY not set in .env")
    _client = Groq(api_key=key)
    return _client


# ── SUGGESTION SYSTEM PROMPT ───────────────────────────────────────────────────

_SUGGEST_SYSTEM = """You are a shopping query suggestion engine for an India-focused e-commerce assistant.

Your task: Given the user's raw, possibly messy query, understand their ACTUAL shopping intent and generate 3-4 refined, clear query suggestions.

RULES:
1. Understand the full intent: product/category, brand, purpose/occasion, budget, color, size, specs, features, comparison requests.
2. Preserve EVERYTHING the user mentioned — gender (men/women/kids), budget, brand, color, fabric/material (e.g. cotton blend), occasion, purpose, specs. Do NOT drop any mentioned constraint.
3. Do NOT invent new constraints the user never mentioned (no adding budget if not mentioned, no adding specs not mentioned).
4. Fix typos and grammar but keep the meaning exactly aligned.
5. Generate DIFFERENT phrasings of the SAME intent — not completely different requests.
6. If user query is vague (e.g. "party wear"), generate suggestions that clarify but do NOT assume a specific subcategory like "dress" or "shoes" — instead ask about the type OR provide general phrasings.
7. Keep suggestions natural, complete, and immediately usable as a shopping chatbot query. Never produce incomplete sentence fragments (e.g. never "Show me for office under ₹1k").
8. For budget: if user wrote "2000" or "2k" or "2000 rupees", use "under ₹2,000" in suggestions.
9. Return ONLY a JSON array of 3-4 suggestion strings. No markdown, no explanation.

OUTPUT FORMAT (array of strings only):
["suggestion 1", "suggestion 2", "suggestion 3", "suggestion 4"]

EXAMPLES:
Input: "suggest office waer for mens cooton blend under 1000"
Output: ["Show me men's office wear in cotton blend under ₹1,000", "Suggest the best men's cotton blend office wear under ₹1,000", "Find men's cotton blend office wear below ₹1,000", "What are the best men's cotton blend office wear options under ₹1,000?"]

Input: "show me blutooth hedphones under 2000"
Output: ["Show me Bluetooth headphones under ₹2,000", "Suggest the best Bluetooth headphones under ₹2,000", "Find good Bluetooth headphones below ₹2,000", "Show me Bluetooth headphones under ₹2,000 with good ratings"]

Input: "best laptop for coding"
Output: ["Best laptop for coding", "Suggest a good laptop for programming and coding", "Find a laptop suitable for coding and development", "What are the best laptops for coding work?"]

Input: "nike shoes blue under 3000"
Output: ["Show me blue Nike shoes under ₹3,000", "Find Nike shoes in blue color under ₹3,000", "Suggest blue Nike shoes below ₹3,000", "Best Nike blue shoes under ₹3,000"]
"""


# ── RULE-BASED FALLBACK ────────────────────────────────────────────────────────

def _rule_based_suggestions(raw_query: str, qu) -> list[str]:
    """
    Generates complete, grammatical rule-based suggestions when LLM is unavailable.
    Preserves gender, category, fabric/material, use case, brand, and budget.
    """
    # 1. Gender / Audience
    gender_prefix = ""
    if getattr(qu, 'gender', None):
        g_map = {'men': "men's", 'women': "women's", 'kids': "kids'", 'unisex': "unisex"}
        gender_prefix = g_map.get(qu.gender, f"{qu.gender}'s")

    # 2. Brands
    brand_prefix = " & ".join(qu.brands) if qu.brands else ""

    # 3. Fabric / Material / Color / Specs
    material_str = ""
    if qu.specifications and 'material' in qu.specifications:
        material_str = qu.specifications['material']

    color_str = f"in {qu.color}" if qu.color else ""

    other_specs = []
    if qu.specifications:
        for k, v in qu.specifications.items():
            if k != 'material':
                other_specs.append(f"with {v}")

    # 4. Product / Category noun
    cat_str = qu.category or ""
    if not cat_str:
        # Extract product noun phrase from normalized or raw query
        clean_core = getattr(qu, 'normalized_query', raw_query).lower()
        clean_core = re.sub(r'\b(?:suggest|show\s+me|find\s+me|recommend|give\s+me|get\s+me|i\s+need|i\s+want|looking\s+for|please|pls)\b', '', clean_core)
        clean_core = re.sub(r'\b(?:under|below|less\s+than|upto?|up\s+to|within|max)\s*[₹₨$rs\.]*\s*\d[\d,]*\s*(?:k\b|thousand\b)?', '', clean_core)
        clean_core = re.sub(r'\b\d[\d,]*\s*(?:k\b|thousand\b)?\b', '', clean_core)
        clean_core = re.sub(r'\b(?:for\s+mens?|for\s+womens?|mens?|womens?|kids?)\b', '', clean_core)
        clean_core = re.sub(r'\b(?:cotton\s+blend|pure\s+cotton|cotton|linen|denim|silk|leather|polyester)\b', '', clean_core)
        clean_core = re.sub(r'\s+', ' ', clean_core).strip()
        cat_str = clean_core or "products"

    # 5. Use Case (e.g. office, gym, gaming) — only if not already part of cat_str
    use_case_str = ""
    if qu.use_case and qu.use_case.lower() not in cat_str.lower():
        use_case_str = f"for {qu.use_case}"

    # 6. Budget
    price_str = ""
    if qu.price.get("max"):
        price_val = qu.price["max"]
        price_str = f"under ₹{price_val:,}"

    # Assemble core phrase with correct natural word ordering
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

    # Comparison intent
    if qu.intent == "comparison" or len(qu.brands) >= 2:
        brands_str = " vs ".join(qu.brands) if qu.brands else core
        return [
            f"Compare {brands_str}",
            f"Which is better: {brands_str}?",
            f"{brands_str} comparison",
            f"Compare top options for {brands_str}",
        ]

    # Full, natural query suggestions
    return [
        f"Show me {core}",
        f"Suggest the best {core}",
        f"Find good {core}",
        f"What are the best options for {core}?",
    ]


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

_suggestion_cache: dict[tuple, list[str]] = {}  # simple in-process cache

def get_query_suggestions(raw_query: str, language: str = "en") -> list[str]:
    """
    Returns 3-4 intent-aware shopping query suggestions for the given raw user input.

    Args:
        raw_query: The raw user input (possibly with typos, vague language).
        language: Response language hint ('en', 'hi', 'hinglish').

    Returns:
        A list of 3-4 suggestion strings.
    """
    if not raw_query or len(raw_query.strip()) < 3:
        return []

    # Cache lookup (normalise key)
    cache_key = (raw_query.strip().lower(), language)
    if cache_key in _suggestion_cache:
        print(f"[Suggest] Cache hit for {raw_query!r}")
        return _suggestion_cache[cache_key]

    # Evict oldest entry if cache is large
    if len(_suggestion_cache) >= 256:
        _suggestion_cache.pop(next(iter(_suggestion_cache)))

    # Step 1: Deterministic query understanding for structured context
    try:
        from src.query_understanding import understand
        qu = understand(raw_query)
    except Exception as e:
        print(f"[Suggest] QU failed: {e}")
        qu = None

    # Step 2: Build context summary for LLM
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

    user_prompt = "\n".join(context_lines) + lang_note + "\n\nGenerate 3-4 refined query suggestions (JSON array only):"

    # Step 3: Call Groq LLM
    try:
        client = _get_client()
        t0 = time.time()
        resp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": _SUGGEST_SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        elapsed = time.time() - t0
        raw_resp = resp.choices[0].message.content.strip()
        print(f"[Suggest] LLM response in {elapsed:.2f}s: {raw_resp[:120]}")

        # Parse JSON array
        # Strip markdown code fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw_resp)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()

        suggestions = json.loads(cleaned)
        if isinstance(suggestions, list):
            # Validate: each entry must be a non-empty string
            suggestions = [str(s).strip() for s in suggestions if isinstance(s, str) and s.strip()]
            if suggestions:
                result = suggestions[:4]
                _suggestion_cache[cache_key] = result
                return result

    except Exception as e:
        print(f"[Suggest] LLM call failed: {e}")

    # Step 4: Fallback to rule-based
    if qu:
        result = _rule_based_suggestions(raw_query, qu)
        _suggestion_cache[cache_key] = result
        return result

    # Last resort: simple rewording
    result = [
        f"Show me {raw_query}",
        f"Suggest the best {raw_query}",
        f"Find good {raw_query}",
    ]
    _suggestion_cache[cache_key] = result
    return result
