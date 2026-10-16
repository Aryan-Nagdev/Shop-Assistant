"""
llm_reason.py  –  LLM-powered deep query understanding via Groq (openai/gpt-oss-20b)
──────────────────────────────────────────────────────────────────────────────
v2 Fixes:
  1. Audio type strictly enforced — earbuds/earphones/headphones never mixed
  2. Count extraction — "suggest 2" → 2; "t shirts 6" → 6; no mention → null (default 6)
  3. Vague expansions — cheap/premium/camera/battery converted to concrete search terms
  4. Feature extraction — processor, RAM, storage, camera MP, style, fit extracted
  5. search_queries use exact audio_type word always
"""
import os, sys, json, re
import config
from dotenv import load_dotenv
load_dotenv()

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
                     CRITICAL: A query for ONE product with features (e.g. "Phone with a good camera and long battery life")
                     is NEVER multi_item! It is "product_search" or "recommendation" for a single product.
                     search_required: true

SEARCH_REQUIRED RULES:
Set search_required = false when:
  - intent is "information" (e.g. concept questions, material science, "Tell me about [material] used for [part]... properties, benefits, tradeoffs")
  - intent is "comparison" AND conceptual/general AND no specific "best products" or price asked (e.g. "Nike or Adidas for running?")
  - user says "just explain", "just tell me", "just compare", "only explain", "don't recommend"
Set search_required = true when:
  - intent is "recommendation" or "product_search" or "multi_item"
  - user asks for "best" products or top models, even without a price (e.g. "What are the best Dell and HP gaming laptops?", "What are the best running shoes?") -> search_required: true!
  - intent is "comparison" AND a price constraint is present (under ₹X, below ₹X, etc.)
  - user explicitly requests products/prices/listings

CRITICAL DISTINCTION:
  "Nike or Adidas for running?"  → comparison, search_required: false
  "What are the best Dell and HP gaming laptops?" → comparison, search_required: true (user asked for top laptop recommendations from both brands)
  "Compare Nike and Adidas shoes under ₹5000" → comparison, search_required: true
  "Which earbuds are best?" → recommendation, search_required: true
  "Tell me about Copper / Brass used for the Rivets... properties, benefits, tradeoffs" → information, search_required: false (material science question, NO product cards)
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

FEATURE EXTRACTION RULES — STRICT:
- processor: Extract EXACTLY as stated — "i7", "i5", "i3", "Ryzen 5", "Snapdragon 8 Gen 3".
  NEVER omit processor if user states one. "i5 laptop" → processor: "i5".
- ram: Extract with unit — "16GB", "8GB". NEVER omit if stated. "16GB RAM" → ram: "16GB".
- storage: Extract with unit — "512GB", "128GB", "1TB". "128GB storage" → storage: "128GB".
  128GB and 256GB are realistic phone storage. 512GB is realistic laptop storage.
- camera: Extract MP or type — "108MP", "50MP", "triple camera".
- battery: Extract mAh EXACTLY — "10000mAh", "5000mAh". A 10,000mAh battery is a power bank / tablet.
  For phones typical is 4000-6000mAh. Extract whatever user says, do not change it.
- style (fashion): "printed", "solid", "casual", "formal", "slim fit", "oversized", etc.
- fabric: Extract EXACTLY — "cotton", "denim", "linen", "polyester", "silk", "leather".
  CRITICAL: "cotton t-shirt" → fabric: "cotton". "denim jacket" → fabric: "denim".
  "leather shoes" → fabric: "leather". NEVER ignore material/fabric if user mentions it.
- fit: "slim", "regular", "loose", "skinny", "relaxed".

BUDGET REALISM RULES:
- NEVER substitute a completely different product just because the exact product is too expensive.
  Example: User asks for laptop under ₹5000 → respond that laptops don't exist that cheaply,
  NOT by showing phone cases or accessories.
- Realistic Indian price floors:
  Laptop: ₹18,000 minimum. Under ₹15,000 = unrealistic for laptop.
  Phone: ₹4,000 minimum. Under ₹2,000 = unrealistic for smartphone.
  Earbuds (TWS): ₹499 minimum. Under ₹300 = unrealistic.
  T-shirt: ₹199 minimum.
  Shoes: ₹399 minimum.
- When budget is unrealistic: set search_queries to search for the cheapest valid option
  (e.g., "cheapest laptop India" instead of "laptop under ₹5000").

MATERIAL / SPEC INTEGRITY RULES:
- If user asks for "cotton t-shirt" — search_queries MUST include "cotton" in every query.
- If user asks for "denim jacket" — search_queries MUST include "denim" or "denim jacket".
- If user asks for "leather shoes" — search_queries MUST include "leather shoes".
- If user asks for i5 laptop — search_queries MUST include "i5" or "Intel Core i5".
- If user asks for 16GB RAM — search_queries MUST include "16GB" or "16GB RAM".
- NEVER drop explicitly stated specs from search queries.

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
- Build 1-3 ready-to-use Google Shopping search strings for India.
- Include ALL relevant features, price constraints, brand, and "India" in every query.
- PRESERVE all user-specified specs in queries — processor, RAM, storage, material, battery.
- For audio: ALWAYS use the EXACT audio_type word in every search query.
  ✓ "boAt earbuds under 2000 India" (if audio_type=earbuds)
  ✗ "boAt audio under 2000 India"   (wrong — too generic)
- For comparison: one query per brand.
- Include tech specs in query when mentioned: "HP laptop Intel i5 16GB RAM 512GB SSD India"
- Include material in fashion queries: "men cotton printed t-shirt under 500 India"
- search_queries may be empty list when search_required is false.
- For variety: use slightly different phrasing across queries (e.g., brand first vs specs first).

CRITICAL RULES:
- "compare X vs Y" or "X vs Y" → ALWAYS comparison.
- "X or Y for running?" → comparison, search_required: false (no buy signal, no price).
- "is X better than Y" / "which is better X or Y" → comparison or information.
- "difference between brand A and brand B" → comparison.
- "difference between X and Y" with NO brand names → information.
- earbuds and earphones and headphones are completely different — NEVER mix them.
- If count is 1 and intent is recommendation → single best item only.
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
- NEVER replace the requested product type with an unrelated product because budget is low.
  Instead, find the cheapest valid product or explain the budget is unrealistic.
"""


def llm_reason(query: str, language: str = 'en') -> dict:
    """
    Deep query understanding via Groq.
    Returns dict with intent, explanation, items, count, features,
    vague_expansions, search_queries, confidence.
    Never raises — returns safe fallback on any error.
    Retries once on timeout to avoid non-deterministic failures.
    """
    _FALLBACK = {
        'intent': None, 'explanation': '', 'items': [], 'count': None,
        'features': {}, 'vague_expansions': [], 'search_queries': [],
        'confidence': 0.0,
    }

    raw = ''

    def _attempt(timeout_secs: float) -> dict | None:
        nonlocal raw
        try:
            from src.language_helper import get_language_prompt_directive
            lang_prompt = get_language_prompt_directive(language)
            effective_system = f"{_SYSTEM}\n\n{lang_prompt}"

            client = _get_client()
            import random as _random
            # Vary temperature dynamically for repeated queries to get diverse, fresh responses like ChatGPT
            temp = 0.65 + (_random.random() * 0.2)
            raw = ""
            for model_candidate in config.GROQ_MODELS:
                try:
                    resp = client.chat.completions.create(
                        model=model_candidate,
                        messages=[
                            {"role": "system", "content": effective_system},
                            {"role": "user",   "content": query.strip()},
                        ],
                        response_format={"type": "json_object"},
                        temperature=temp,
                        max_tokens=2048,
                        timeout=timeout_secs,
                    )
                    content = (resp.choices[0].message.content or "").strip()
                    if content:
                        raw = content
                        break
                except Exception as ex_m:
                    print(f"[LLM] Model {model_candidate} call failed: {ex_m}")
                    continue

            raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.DOTALL).strip()
            if not raw:
                return None

            data = json.loads(raw, strict=False)

            valid_intents = ('information', 'comparison', 'recommendation', 'product_search', 'multi_item')
            if data.get('intent') not in valid_intents:
                _LEGACY_MAP = {'answer_only': 'information'}
                legacy = _LEGACY_MAP.get(data.get('intent'))
                if legacy:
                    data['intent'] = legacy
                else:
                    print(f"[LLM] Unknown intent '{data.get('intent')}', using fallback")
                    return None

            features = data.get('features') or {}
            audio_type = (features.get('audio_type') or '').strip().lower()
            valid_audio = ('earbuds', 'earphones', 'headphones', 'neckband', 'speaker')
            if audio_type not in valid_audio:
                audio_type = None
            else:
                features['audio_type'] = audio_type

            raw_count = data.get('count')
            count = None
            if raw_count is not None:
                try:
                    count = int(raw_count)
                    if count <= 0:
                        count = None
                except (TypeError, ValueError):
                    count = None

            _CANONICAL_MAP = {
                'information':    'information',
                'comparison':     'comparison',
                'recommendation': 'recommendation',
                'product_search': 'product_search',
                'multi_item':     'recommendation',
            }
            raw_intent = data.get('intent')
            canonical_intent = _CANONICAL_MAP.get(raw_intent, 'recommendation')

            llm_search_required = data.get('search_required')
            if llm_search_required is None:
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
            return None
        except Exception as e:
            err_str = str(e)
            if 'timeout' in err_str.lower() or 'timed out' in err_str.lower() or 'read timeout' in err_str.lower():
                # Propagate timeout as a specific signal so caller can retry
                raise TimeoutError(f"Groq timeout: {e}")
            print(f"[LLM] Groq call failed: {e}")
            return None

    # First attempt — 5s (fast path)
    try:
        result = _attempt(5.0)
        if result is not None:
            return result
    except TimeoutError:
        print("[LLM] First attempt timed out — retrying with 9s limit...")
        try:
            result = _attempt(9.0)
            if result is not None:
                return result
        except TimeoutError:
            print("[LLM] Second attempt also timed out — using QU/NLU fallback.")
        except Exception as e:
            print(f"[LLM] Retry failed: {e}")
    except Exception as e:
        print(f"[LLM] Groq call failed: {e}")

    return _FALLBACK