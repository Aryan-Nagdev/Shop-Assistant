"""
llm_reason.py  –  LLM-powered deep query understanding via Groq (llama3-70b)
──────────────────────────────────────────────────────────────────────────────
v2 Fixes:
  1. Audio type strictly enforced — earbuds/earphones/headphones never mixed
  2. Count extraction — "suggest 2" → 2; "t shirts 6" → 6; no mention → null (default 6)
  3. Vague expansions — cheap/premium/camera/battery converted to concrete search terms
  4. Feature extraction — processor, RAM, storage, camera MP, style, fit extracted
  5. search_queries use exact audio_type word always
"""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


_SYSTEM = """You are a query understanding engine for an India e-commerce shopping assistant.
Analyse the user query and return ONLY valid JSON — no markdown, no explanation outside JSON.

OUTPUT SCHEMA:
{
  "intent": <string>,
  "search_required": <boolean>,
  "explanation": <string>,
  "items": <list of strings>,
  "count": <int or null>,
  "features": {
    "processor": <string or null>,
    "ram": <string or null>,
    "storage": <string or null>,
    "display": <string or null>,
    "camera": <string or null>,
    "battery": <string or null>,
    "style": <string or null>,
    "fabric": <string or null>,
    "fit": <string or null>,
    "audio_type": <string or null>,
    "other": <list of strings>
  },
  "vague_expansions": <list of strings>,
  "search_queries": <list of objects with keys label and query>,
  "confidence": <float 0-1>
}

INTENT RULES (pick exactly one):
- "information"    → User wants an explanation or answer. NOT looking for products to buy.
                     TRUE information: "what is ANC", "what is AMOLED", "is OLED better than LCD",
                     "explain noise cancellation", "what is 5G", "how does NFC work"
                     ALSO information: "is OLED better than LCD" (concept question, no buy intent)
                     RULE: If the query has NO product noun and NO buy intent → "information".
                     search_required: false

- "comparison"     → User wants to compare brands, products, or technologies.
                     Examples: "Nike vs Adidas for running", "boAt vs JBL earbuds",
                     "iPhone vs Samsung", "AirPods vs Galaxy Buds"
                     search_required: FALSE when comparing at a general/conceptual level (no price).
                     search_required: TRUE when user also wants current products/prices
                     (e.g. "compare Nike and Adidas shoes under ₹5,000").

- "recommendation" → User wants products suggested/recommended.
                     Examples: "which earbuds are best?", "suggest a laptop for coding",
                     "what phone should I buy?", "good earbuds for gym",
                     "which running shoes are best?"
                     search_required: true

- "product_search" → User gives explicit shopping requirements (brand/category + price/specs).
                     Examples: "Nike shoes under 3000", "i5 laptop 16GB under 50k",
                     "Samsung phone under 20k", "blue earbuds under 2k"
                     search_required: true

- "multi_item"     → User asks for multiple DIFFERENT product types in one query.
                     Examples: "jeans + t-shirt + sneakers", "phone and earbuds combo"
                     search_required: true

SEARCH_REQUIRED RULES:
Set search_required = false when:
  - intent is "information"
  - intent is "comparison" AND no price constraint AND no explicit buy/find/show/products signal
  - user says "just explain", "just tell me", "just compare", "only explain", "don't recommend"
Set search_required = true when:
  - intent is "recommendation" or "product_search" or "multi_item"
  - intent is "comparison" AND a price constraint is present (under ₹X, below ₹X, etc.)
  - user explicitly requests products/prices/listings

CRITICAL DISTINCTION:
  "Nike or Adidas for running?"  → comparison, search_required: false
  "Compare Nike and Adidas shoes under ₹5000" → comparison, search_required: true
  "Which earbuds are best?" → recommendation, search_required: true
  "What is ANC?" → information, search_required: false

AUDIO TYPE RULE — CRITICAL:
features.audio_type MUST be set to EXACTLY ONE of: earbuds, earphones, headphones, neckband, speaker
- "earbuds" = TWS/True Wireless / wireless buds (e.g. boAt Airdopes, Samsung Galaxy Buds)
- "earphones" = wired in-ear with cable (e.g. boAt BassHeads, JBL C100SI)
- "headphones" = over-ear or on-ear cups (e.g. Sony WH-1000XM5, boAt Rockerz)
- "neckband" = behind-neck band style (e.g. boAt Rockerz 255)
- "speaker" = Bluetooth / portable speaker
NEVER return earbuds results for headphones query or vice versa.
If query says "earbuds" → audio_type = "earbuds", search_queries use word "earbuds" only.
If query says "earphones" → audio_type = "earphones", search_queries use word "earphones" only.
If query says "headphones" → audio_type = "headphones", search_queries use word "headphones" only.

COUNT RULES:
- "count": Extract the EXACT number the user wants returned.
  - "suggest 2 phones" → 2
  - "one best laptop" → 1  
  - "show me 3 earbuds" → 3
  - "t shirts 6" → 6
  - No number mentioned → null  (system will default to 6)
- count must be an integer or null. Never a string.

FEATURE EXTRACTION RULES:
- processor: Extract exactly — "i7", "i5", "Ryzen 5", "Snapdragon 8 Gen 3", etc.
- ram: Extract with unit — "16GB RAM", "8GB RAM"
- storage: Extract with unit — "512GB SSD", "1TB SSD"
- camera: Extract MP or type — "108MP", "50MP", "triple camera"
- battery: Extract mAh — "5000mAh"
- style (fashion): "printed", "solid", "casual", "formal", "slim fit", "oversized", etc.
- fabric: "cotton", "denim", "linen", "polyester", "silk", etc.
- fit: "slim", "regular", "loose", "skinny", "relaxed"

VAGUE QUERY EXPANSIONS:
Convert vague terms to concrete search strings:
- "cheap" → ["budget", "affordable", "value for money", "low price"]
- "premium" → ["premium", "flagship", "high rated", "best in class"]
- "best camera" → ["high megapixel camera", "108MP", "50MP camera phone"]
- "good battery" → ["5000mAh battery", "long battery life", "battery life"]
- "gaming" → ["gaming performance", "high refresh rate", "dedicated GPU"]
- "fast charging" → ["65W fast charging", "quick charge"]
- "lightweight" → ["lightweight", "thin", "ultrabook", "portable"]

SEARCH QUERY RULES:
- Build 1-3 ready-to-use Google Shopping search strings for India
- Include relevant features, price constraints, brand, and "India"
- For audio: ALWAYS use the EXACT audio_type word in every search query
  ✓ "boAt earbuds under 2000 India" (if audio_type=earbuds)
  ✗ "boAt audio under 2000 India"   (wrong — too generic)
- For comparison: one query per brand
- Include tech specs in query when mentioned: "HP laptop Intel i7 16GB RAM India"
- Include style in fashion queries: "men printed cotton t-shirt under 500 India"
- search_queries may be empty list when search_required is false.

CRITICAL RULES:
- "compare X vs Y" or "X vs Y" → ALWAYS comparison
- "X or Y for running?" → comparison, search_required: false (no buy signal, no price)
- "is X better than Y" / "which is better X or Y" → comparison or information
- "difference between brand A and brand B" → comparison
- "difference between X and Y" with NO brand names → information
- earbuds and earphones and headphones are completely different — NEVER mix them
- If count is 1 and intent is recommendation → single best item only
- explanation: REQUIRED for information (2-4 sentences, plain prose, no markdown).
  REQUIRED for comparison when search_required=false — write a STRUCTURED comparison:
    Line 1: Brief intro (1 sentence).
    Line 2: [Option A]: 2-3 bullet points of key strengths/characteristics.
    Line 3: [Option B]: 2-3 bullet points of key strengths/characteristics.
    Line 4: Use case / who should choose which — be specific about the scenario in the query.
    Line 5: Final verdict sentence: "For [use case], I would recommend [X] because..."
  Use plain text, no markdown bullets. Separate sections with a blank line.
  Empty string ONLY for pure shopping queries (recommendation/product_search).
- items: For comparison list ALL brand/product names. For multi_item list product types. Else empty list.
"""


def llm_reason(query: str, language: str = 'en') -> dict:
    """
    Deep query understanding via Groq llama3-70b.
    Returns dict with intent, explanation, items, count, features,
    vague_expansions, search_queries, confidence.
    Never raises — returns safe fallback on any error.
    """
    _FALLBACK = {
        'intent': None, 'explanation': '', 'items': [], 'count': None,
        'features': {}, 'vague_expansions': [], 'search_queries': [],
        'confidence': 0.0,
    }

    raw = ''
    try:
        from src.language_helper import get_language_prompt_directive
        lang_prompt = get_language_prompt_directive(language)
        effective_system = f"{_SYSTEM}\n\n{lang_prompt}"

        client = _get_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": effective_system},
                {"role": "user",   "content": query.strip()},
            ],
            temperature=0.1,
            max_tokens=800,
            timeout=2.5,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.DOTALL).strip()

        data = json.loads(raw, strict=False)

        valid_intents = ('information', 'comparison', 'recommendation', 'product_search', 'multi_item')
        if data.get('intent') not in valid_intents:
            # Graceful backward compat: map legacy intent names
            _LEGACY_MAP = {'answer_only': 'information'}
            legacy = _LEGACY_MAP.get(data.get('intent'))
            if legacy:
                data['intent'] = legacy
            else:
                print(f"[LLM] Unknown intent '{data.get('intent')}', using fallback")
                return _FALLBACK

        features = data.get('features') or {}
        audio_type = (features.get('audio_type') or '').strip().lower()
        valid_audio = ('earbuds', 'earphones', 'headphones', 'neckband', 'speaker')
        if audio_type not in valid_audio:
            audio_type = None
        else:
            features['audio_type'] = audio_type

        # Validate count is integer
        raw_count = data.get('count')
        count = None
        if raw_count is not None:
            try:
                count = int(raw_count)
                if count <= 0:
                    count = None
            except (TypeError, ValueError):
                count = None

        # Compute canonical intent (maps multi_item -> recommendation for routing)
        _CANONICAL_MAP = {
            'information':   'information',
            'comparison':    'comparison',
            'recommendation': 'recommendation',
            'product_search': 'product_search',
            'multi_item':    'recommendation',  # multi_item still uses recommendation path
        }
        raw_intent = data.get('intent')
        canonical_intent = _CANONICAL_MAP.get(raw_intent, 'recommendation')

        # Extract LLM's search_required assessment
        llm_search_required = data.get('search_required')
        if llm_search_required is None:
            # Default based on canonical intent
            llm_search_required = canonical_intent in ('recommendation', 'product_search', 'multi_item')
        else:
            llm_search_required = bool(llm_search_required)

        result = {
            'intent':           raw_intent,
            'canonical_intent': canonical_intent,
            'search_required':  llm_search_required,
            'explanation':      (data.get('explanation') or '').strip(),
            'items':            data.get('items') or [],
            'count':            count,
            'features':         features,
            'vague_expansions': data.get('vague_expansions') or [],
            'search_queries':   data.get('search_queries') or [],
            'confidence':       float(data.get('confidence', 0.8)),
        }
        print(f"[LLM] intent={raw_intent!r} canonical={canonical_intent!r} "
              f"search_required={llm_search_required} conf={result['confidence']:.2f} "
              f"count={result['count']} audio_type={audio_type}")
        return result

    except json.JSONDecodeError as e:
        print(f"[LLM] JSON parse error: {e} | raw={raw[:300]!r}")
        return _FALLBACK
    except Exception as e:
        print(f"[LLM] Groq call failed: {e}")
        return _FALLBACK