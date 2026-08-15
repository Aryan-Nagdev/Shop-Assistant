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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    key = os.getenv("GROQ_API_KEY", "").strip().strip("'\"")
    if not key:
        raise ValueError("GROQ_API_KEY not set in .env")
    _client = Groq(api_key=key)
    return _client


# ── SUGGESTION SYSTEM PROMPT ───────────────────────────────────────────────────

_SUGGEST_SYSTEM = """You are a shopping query suggestion engine for an India-focused e-commerce assistant.

Your task: Given the user's raw, possibly messy query, understand their ACTUAL shopping intent and generate 3-4 refined, clear query suggestions.

RULES:
1. Understand the full intent: product/category, brand, purpose/occasion, budget, color, size, specs, features, comparison requests.
2. Preserve EVERYTHING the user mentioned — budget, brand, color, occasion, purpose, specs. Do NOT drop any mentioned constraint.
3. Do NOT invent new constraints the user never mentioned (no adding budget if not mentioned, no adding specs not mentioned).
4. Fix typos and grammar but keep the meaning exactly aligned.
5. Generate DIFFERENT phrasings of the SAME intent — not completely different requests.
6. If user query is vague (e.g. "party wear"), generate suggestions that clarify but do NOT assume a specific subcategory like "dress" or "shoes" — instead ask about the type OR provide general phrasings.
7. Keep suggestions natural, complete, and immediately usable as a shopping chatbot query.
8. For budget: if user wrote "2000" or "2k" or "2000 rupees", use "under ₹2,000" in suggestions.
9. Return ONLY a JSON array of 3-4 suggestion strings. No markdown, no explanation.

OUTPUT FORMAT (array of strings only):
["suggestion 1", "suggestion 2", "suggestion 3", "suggestion 4"]

EXAMPLES:
Input: "i want somthing good for party wear"
Output: ["Show me the best options for party wear", "Suggest something stylish and good for a party", "What are some good party-wear options?", "Find trendy party wear outfits"]

Input: "show me blutooth hedphones under 2000"
Output: ["Show me Bluetooth headphones under ₹2,000", "Suggest the best Bluetooth headphones under ₹2,000", "Find good Bluetooth headphones below ₹2,000", "Show me Bluetooth headphones under ₹2,000 with good ratings"]

Input: "best laptop for coding"
Output: ["Best laptop for coding", "Suggest a good laptop for programming and coding", "Find a laptop suitable for coding and development", "What are the best laptops for coding work?"]

Input: "nike shoes blue under 3000"
Output: ["Show me blue Nike shoes under ₹3,000", "Find Nike shoes in blue color under ₹3,000", "Suggest blue Nike shoes below ₹3,000", "Best Nike blue shoes under ₹3,000"]

Input: "gifst for my sister birthday under 2000"
Output: ["Find gifts for my sister's birthday under ₹2,000", "Suggest birthday gift ideas for sister under ₹2,000", "What are good birthday gifts for a sister under ₹2,000?", "Show me birthday gifts under ₹2,000 for sister"]
"""


# ── RULE-BASED FALLBACK ────────────────────────────────────────────────────────

def _rule_based_suggestions(raw_query: str, qu) -> list[str]:
    """
    Generates simple rule-based suggestions when LLM is unavailable.
    Uses structured slots from QueryUnderstanding.
    """
    parts = []
    if qu.brands:
        parts.append(" & ".join(qu.brands))
    if qu.category:
        parts.append(qu.category)
    if qu.color:
        parts.append(f"in {qu.color}")
    if qu.specifications:
        for k, v in list(qu.specifications.items())[:2]:
            parts.append(f"with {v}")
    if qu.use_case:
        parts.append(f"for {qu.use_case}")
    if qu.price.get("max"):
        price_val = qu.price["max"]
        if price_val >= 1000:
            price_str = f"₹{price_val // 1000}k" if price_val % 1000 == 0 else f"₹{price_val:,}"
        else:
            price_str = f"₹{price_val}"
        parts.append(f"under {price_str}")

    if not parts:
        core = raw_query.strip()
        return [
            f"Show me {core}",
            f"Suggest the best {core}",
            f"Find good {core}",
        ]

    core = " ".join(parts)

    suggestions = [
        f"Show me {core}",
        f"Suggest the best {core}",
        f"Find good {core}",
        f"What are the best {core}?",
    ]

    # If comparison intent
    if qu.intent == "comparison" or len(qu.brands) >= 2:
        brands_str = " vs ".join(qu.brands) if qu.brands else core
        suggestions = [
            f"Compare {brands_str}",
            f"Which is better: {brands_str}?",
            f"{brands_str} comparison",
        ]

    return suggestions[:4]


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

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
            model="llama-3.1-8b-instant",  # Fastest Groq model for low latency
            messages=[
                {"role": "system", "content": _SUGGEST_SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=300,
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
                return suggestions[:4]

    except Exception as e:
        print(f"[Suggest] LLM call failed: {e}")

    # Step 4: Fallback to rule-based
    if qu:
        return _rule_based_suggestions(raw_query, qu)

    # Last resort: simple rewording
    return [
        f"Show me {raw_query}",
        f"Suggest the best {raw_query}",
        f"Find good {raw_query}",
    ]
