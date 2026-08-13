"""
chatbot.py – Session-aware orchestrator
v5 — Intent Detection + Search Routing:
  1. Intent classified as: information | comparison | recommendation | product_search
  2. search_required = True/False decided BEFORE any live_search() call
  3. information → LLM text only, NO live_search
  4. comparison (no price/buy signal) → LLM text only, NO live_search
  5. comparison (with price/buy signal) → fetch_comparison() + product cards
  6. recommendation | product_search → fetch_one() + Phase 2/3 pipeline (unchanged)
  7. Priority: explicit no-search signals > deterministic QU > LLM > NLU
  8. All Phase 1/2/3 functionality preserved
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.nlu_engine import analyse, KNOWN_BRANDS
from src.live_search import fetch_one, fetch_comparison, DEFAULT_COUNT
from src.response_builder import build_response
from src.llm_reason import llm_reason
from src.query_understanding import understand_and_log, QueryUnderstanding
from src.conversation_manager import ConversationManager


# ── Comparison patterns (for search_required refinement on comparison intent) ───
_VS_RE = re.compile(
    r'\bvs\.?\b|\bversus\b|\bbetween\b|\bcompare\b|\bwhich\s+(is|has|have|gives?)\b',
    re.I
)
# Explicit no-search instruction detection
_NO_SEARCH_RE = re.compile(
    r'\b(?:just\s+(?:explain|tell|compare|say|show|answer)|'
    r'only\s+(?:explain|tell|compare|answer)|'
    r"don'?t\s+(?:recommend|show|search|find)|'"
    r'no\s+products?|text\s+only|just\s+info|'
    r'explain\s+the\s+difference|'
    r'without\s+(?:products?|links?|cards?))\b',
    re.I,
)
# Explicit product-fetch signals (used to flip comparison to search_required=True)
_PRODUCT_FETCH_RE = re.compile(
    r'\b(?:show\s+me|find\s+me|give\s+me|get\s+me|buy|purchase|order|'
    r'available|products?|listings?|price|'
    r'under\s*[₹₨$]?\s*\d|below\s*[₹₨$]?\s*\d|'
    r'within\s*[₹₨$]?\s*\d|upto?\s*[₹₨$]?\s*\d)\b',
    re.I,
)


class ShopBot:
    """Per-session India e-commerce chatbot."""

    MAX_HISTORY   = 10
    CONTEXT_TURNS = 3

    def __init__(self):
        self.history: list[dict] = []
        self.conversation_mgr = ConversationManager()

    # ── Public ─────────────────────────────────────────────────────────────────
    def chat(self, user_msg: str, language: str = 'auto') -> dict:
        user_msg = user_msg.strip()
        if not user_msg:
            return self._empty()

        # ── Language Detection / Handling ─────────────────────────────────────
        from src.language_helper import detect_language, clean_hindi_query_for_search
        effective_lang = detect_language(user_msg, default_lang='en' if language == 'auto' else language)
        if language in ('hi', 'hinglish'):
            effective_lang = language

        # For Hindi/Hinglish, normalize query terms for slot tracking and QU
        qu_input = clean_hindi_query_for_search(user_msg) if effective_lang in ('hi', 'hinglish') else user_msg
        if not qu_input.strip():
            qu_input = user_msg

        # ── STEP 0a: Conversational Slot Tracking & Query Understanding ────────
        context, qu, effective_q = self.conversation_mgr.process_turn(qu_input)
        print(f"[Bot] Raw: {user_msg!r} [lang={effective_lang}] -> Effective Q: {effective_q!r}")

        search_query_seed = effective_q

        # ── Clarification gate ─────────────────────────────────────────────────
        if qu.needs_clarification and context.is_empty():
            print(f"[Bot] Query too vague — returning clarification.")
            clar_msg = qu.clarification_msg
            if effective_lang == 'hi':
                clar_msg = "कृपया थोड़ा और विवरण दें (जैसे कि आपका बजट, ब्रांड या उत्पाद प्रकार), ताकि मैं आपके लिए सबसे अच्छे उत्पाद खोज सकूँ।"
            elif effective_lang == 'hinglish':
                clar_msg = "Please thoda aur detail batayein (jaise aapka budget, brand ya product type) taaki main best options dhundh sakun."
            
            self._push('user',      user_msg, 'clarification', {})
            self._push('assistant', clar_msg, 'clarification', {})
            return {
                'answer':           clar_msg,
                'intent':           'clarification',
                'search_required':  False,
                'entities':         {},
                'products':         [],
                'language':         effective_lang,
            }

        # ── STEP 0b: LLM reasoning ──────────────────────────────────────────
        llm = llm_reason(effective_q, language=effective_lang)
        explanation = llm.get('explanation', '')

        # ── STEP 1: NLU ──────────────────────────────────────────────────────
        nlu     = analyse(search_query_seed)
        ents    = nlu['entities']
        queries = nlu['queries']

        # ── STEP 1a: Apply QU findings (HIGHEST PRIORITY) ─────────────────────
        self._apply_qu_to_ents(qu, ents)

        # ── STEP 1b: Merge LLM enrichments (LOWEST PRIORITY) ──────────────────
        ents = self._merge_llm_into_ents(ents, llm, queries)

        # ── STEP 2: Resolve final intent + search_required ─────────────────────
        intent, search_required = self._resolve_intent_and_search(
            llm, qu, nlu, user_msg, ents
        )

        # ── STEP 2b: Rebuild queries correctly per intent ──────────────────────
        if intent == 'comparison' and search_required:
            queries = self._build_comparison_queries(search_query_seed, ents, llm)
        elif intent in ('comparison', 'information') and not search_required:
            queries = []  # No search queries needed for text-only responses
        elif llm.get('search_queries') and (
            not queries or queries[0].get('query', '').startswith('Results')
        ):
            lq = llm['search_queries']
            if isinstance(lq, list) and lq:
                queries = [
                    {'label': q.get('label', 'Results'), 'query': q.get('query', '')}
                    for q in lq if q.get('query')
                ]

        safe_queries = [q['query'].replace('₹', 'Rs.') for q in queries]
        print(f"[Bot] intent={intent!r} search_required={search_required} "
              f"| lang={effective_lang} | brands={ents.get('brands')} | count={ents.get('count')} "
              f"| audio={ents.get('audio_type')} "
              f"| queries={safe_queries}")

        # ── STEP 3: Routing — search_required gates ALL live_search() calls ─────
        products    = []
        brands_data = None

        if not search_required:
            # ── TEXT-ONLY PATH: no live_search() called ────────────────────────
            text  = self._generate_text_answer(intent, explanation, user_msg, ents)
            cards = []

        else:
            # ── SEARCH PATH: existing Phase 2/3 pipeline ───────────────────────
            if intent == 'comparison':
                brands_data = fetch_comparison(queries, ents, per_brand=3)
                for prods in brands_data.values():
                    products.extend(prods)

            elif intent in ('recommendation', 'product_search'):
                nlu_intent_raw = nlu.get('intent', '')
                if nlu_intent_raw == 'single_best':
                    prods    = fetch_one(queries[0]['query'] if queries else search_query_seed, ents, top_n=3)
                    products = prods[:1]
                    intent   = 'single_best'
                elif nlu_intent_raw == 'multi_item':
                    brands_data = {}
                    for q_info in queries:
                        item_ents = dict(ents)
                        item_ents['audio_type'] = None
                        item_ents['count']      = None
                        prods = fetch_one(q_info['query'], item_ents, top_n=2)
                        brands_data[q_info['label']] = prods
                        products.extend(prods)
                    intent = 'multi_item'
                else:
                    if queries:
                        products = fetch_one(queries[0]['query'], ents, top_n=DEFAULT_COUNT)

            else:
                if queries:
                    products = fetch_one(queries[0]['query'], ents, top_n=DEFAULT_COUNT)

            # ── STEP 4: Build response ─────────────────────────────────────────
            text, cards = build_response(
                intent, ents, user_msg, products, brands_data,
                llm_explanation=explanation,
                language=effective_lang,
            )

        # ── STEP 5: Update history ─────────────────────────────────────────────
        self._push('user',      user_msg, intent, ents)
        self._push('assistant', text,     intent, {})

        # ── Persist intent to context for follow-up routing ────────────────────
        context.last_intent = intent
        if intent == 'comparison':
            cmp_brands = list(ents.get('brands', []))
            for item in (llm.get('items') or []):
                if item and item not in cmp_brands:
                    cmp_brands.append(item)
            for b_lower, b_display in KNOWN_BRANDS.items():
                if b_lower in user_msg.lower() and b_display not in cmp_brands:
                    cmp_brands.append(b_display)
            if cmp_brands:
                context.last_comparison_items = cmp_brands

        # ── STEP 6: Structured Debug Log ───────────────────────────────────────
        self._log_debug_block(user_msg, qu, effective_q, queries, cards, text,
                              intent, search_required)

        ents_out = dict(ents)
        if 'qu' in ents_out and hasattr(ents_out['qu'], 'to_dict'):
            ents_out['qu'] = ents_out['qu'].to_dict()

        # Patch final intent + search_required onto Phase 1 structured query output
        qu_dict = qu.to_dict()
        qu_dict['intent'] = intent
        qu_dict['search_required'] = search_required

        return {
            'answer':           text,
            'intent':           intent,
            'search_required':  search_required,
            'entities':         ents_out,
            'products':         cards,
            'structured_query': qu_dict,
            'language':         effective_lang,
        }

    def _log_debug_block(self, user_msg: str, qu: QueryUnderstanding, effective_q: str,
                          queries: list, products: list, text: str,
                          intent: str = '', search_required: bool | None = None):
        print("\n========== SHOP SEARCH DEBUG ==========")
        print(f"Original Query:\n{user_msg}")
        print(f"\nDetected Intent:    {intent}")
        print(f"Search Required:    {search_required}")
        print(f"\nPhase 1 Structured Query:\n{qu.to_dict()}")
        print(f"\nNormalized Query:\n{effective_q}")
        print(f"\nSearch Queries:\n{[q.get('query') for q in queries] if queries else ['(none — text-only response)']}")
        print(f"\nProducts Returned ({len(products)}):")
        for i, p in enumerate(products, 1):
            alt = f" [ALTERNATIVE: {p.get('alternative_diff')}]" if p.get('is_alternative') else ""
            print(f"  {i}. {p.get('title')} | {p.get('price_inr')}{alt}")
        print(f"\nPhase 3 Executed:\n{any(p.get('is_alternative') for p in products)}")
        print(f"\nFinal Response:\n{text}")
        print("========================================\n")

    def clear(self):
        self.history.clear()
        self.conversation_mgr.context.clear()

    # ── Private ────────────────────────────────────────────────────────────────

    def _resolve_intent_and_search(
        self, llm: dict, qu: 'QueryUnderstanding', nlu: dict, user_msg: str, ents: dict
    ) -> tuple[str, bool]:
        """
        Resolve final (intent, search_required) from all signals.

        Priority:
          1. Explicit no-search user instructions ("just tell me", "don't recommend")
          2. Deterministic QU pre-classification (from query_understanding.py)
          3. LLM canonical_intent + search_required (when conf >= 0.65)
          4. Conversation follow-up context (inherit comparison if prev turn was comparison)
          5. NLU intent (fallback)
        """
        conf          = llm.get('confidence', 0.0)
        llm_canonical = llm.get('canonical_intent')      # already mapped to 4-way schema
        llm_search    = llm.get('search_required')       # LLM's own assessment
        qu_intent     = qu.intent                        # deterministic pre-class
        qu_search     = qu.search_required               # deterministic pre-class
        last_intent   = self.conversation_mgr.context.last_intent

        # ── Priority 1: Explicit no-search instruction in raw user message ──────
        if _NO_SEARCH_RE.search(user_msg):
            print(f"[Bot] Explicit no-search instruction detected.")
            if _VS_RE.search(user_msg) or llm_canonical == 'comparison':
                return 'comparison', False
            return 'information', False

        # ── Priority 2: Deterministic QU with a clear signal ────────────────────
        # QU returns None when ambiguous — only trust it when it has a clear signal.
        if qu_intent is not None and qu_search is not None:
            if qu_intent == 'information':
                print(f"[Bot] QU says information → no search.")
                return 'information', False

            if qu_intent == 'comparison':
                # Comparison queries without price/search signals do NOT require live product search
                has_search_trigger = (
                    qu.price.get('max') is not None
                    or bool(re.search(r'\b(?:show|find|buy|price|under|below|get|products?|listings?)\b', user_msg, re.I))
                )
                if has_search_trigger:
                    search_req = True
                elif llm_canonical == 'comparison' and llm_search is not None and conf >= 0.70 and has_search_trigger:
                    search_req = llm_search
                else:
                    search_req = qu_search if qu_search is not None else False
                print(f"[Bot] QU comparison → search_required={search_req}")
                return 'comparison', search_req

        # ── Priority 3: LLM when conf >= 0.65 ────────────────────────────────────
        if llm_canonical and conf >= 0.65:
            if llm_canonical == 'comparison':
                search_req = False if not (qu.price.get('max') is not None or bool(re.search(r'\b(?:show|find|buy|price|under|below|get|products?|listings?)\b', user_msg, re.I))) else (llm_search or False)
            else:
                search_req = llm_search if llm_search is not None else (llm_canonical != 'information')
            print(f"[Bot] LLM intent={llm_canonical!r} search_required={search_req} (conf={conf:.2f})")
            return llm_canonical, search_req

        # ── Priority 4: Deterministic QU recommendation/product_search fallback ─
        if qu_intent in ('recommendation', 'product_search') and qu_search is not None:
            print(f"[Bot] QU {qu_intent} fallback (search_required={qu_search})")
            return qu_intent, qu_search

        # ── Priority 5: Conversation follow-up context ────────────────────────
        # Short/ambiguous follow-up after a comparison → stay in comparison mode.
        # e.g. "Which one is better for beginners?" after "Nike vs Adidas"
        words = user_msg.split()
        is_short_followup = len(words) <= 8 and not _PRODUCT_FETCH_RE.search(user_msg)
        if is_short_followup and last_intent == 'comparison':
            print(f"[Bot] Short follow-up after comparison → continuing comparison (search_required=False)")
            return 'comparison', False

        # ── Priority 6: NLU fallback ───────────────────────────────────────────
        nlu_intent_raw = nlu.get('intent', 'product_search')
        _NLU_INTENT_MAP = {
            'info_only':      ('information',   False),
            'comparison':     ('comparison',    False),
            'single_best':    ('recommendation', True),
            'multi_item':     ('recommendation', True),
            'product_search': ('product_search', True),
        }
        intent, search_req = _NLU_INTENT_MAP.get(nlu_intent_raw, ('product_search', True))
        print(f"[Bot] NLU fallback: intent={intent!r} search_required={search_req}")
        return intent, search_req

    def _generate_text_answer(
        self, intent: str, explanation: str, query: str, ents: dict
    ) -> str:
        """
        Generate a natural language text answer without product cards.
        Used when search_required = False.
        Comparison → structured format (Option A / Option B / use case / verdict).
        Information → concise expert explanation.
        """
        # LLM already provided an explanation via llm_reason — prefer it
        if explanation and len(explanation) > 60:
            nudge = (
                "\n\n↪ *Want me to search for actual products with live ₹ prices? Just ask!*"
                if intent == 'comparison'
                else "\n\n↪ *Want me to find or compare actual products? Just ask!*"
            )
            return explanation + nudge

        # Explanation was missing or too short — generate via inline Groq call
        try:
            import os
            from groq import Groq
            key = os.getenv("GROQ_API_KEY", "").strip().strip("'\"")
            if not key:
                raise ValueError("No API key")

            client = Groq(api_key=key)

            if intent == 'information':
                system_prompt = (
                    "You are a helpful India e-commerce and technology expert assistant.\n"
                    "Answer the user's question clearly and concisely in 2-4 sentences.\n"
                    "Be direct and accurate. Use plain prose. No markdown. "
                    "Do NOT recommend or mention specific products unless asked."
                )
                user_content = query
                max_tok = 300

            else:  # comparison
                brands = ents.get('brands', [])
                dept = ents.get('dept') or ents.get('category') or 'products'

                system_prompt = (
                    "You are a knowledgeable India e-commerce shopping expert.\n"
                    "The user wants to compare options. Give a structured, helpful comparison.\n\n"
                    "FORMAT (use plain text, NO markdown, NO bullet points, NO asterisks):\n"
                    "Paragraph 1: One-sentence intro about both options.\n"
                    "Paragraph 2: [First option] — describe 2-3 key strengths or characteristics "
                    "relevant to the user's use case.\n"
                    "Paragraph 3: [Second option] — describe 2-3 key strengths or characteristics "
                    "relevant to the user's use case.\n"
                    "Paragraph 4: Use case guidance — who should choose which, based on the "
                    "specific context in the user's query (e.g. running, gaming, coding, etc.).\n"
                    "Final sentence: Clear verdict starting with 'For [use case], I would recommend [X] because...'"
                )
                brand_ctx = f" (brands: {', '.join(brands)}" if brands else ""
                user_content = f"{query}{brand_ctx}"
                max_tok = 600

            history_msgs = []
            for h in self.history[-4:]:
                if h.get('role') in ('user', 'assistant') and h.get('content'):
                    history_msgs.append({'role': h['role'], 'content': h['content']})

            messages = [{"role": "system", "content": system_prompt}] + history_msgs + [{"role": "user", "content": user_content}]

            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.35,
                max_tokens=max_tok,
                timeout=6.0,
            )
            ans = resp.choices[0].message.content.strip()
            nudge = (
                "\n\n↪ *Want me to search for actual products with live ₹ prices? Just ask!*"
                if intent == 'comparison'
                else "\n\n↪ *Want me to find or compare actual products? Just ask!*"
            )
            return ans + nudge

        except Exception as e:
            print(f"[Bot] _generate_text_answer fallback LLM failed: {e}")

        # Hard fallback
        if intent == 'comparison':
            return (
                "Both are strong options depending on your specific needs. "
                "For a detailed comparison with live prices, try asking: "
                "*\"Compare [Brand A] vs [Brand B] under ₹X\"*"
            )
        return (
            "That's a great question! For specific product help, ask me to **find**, "
            "**recommend**, or **compare** — I'll pull live Indian store results with ₹ prices."
        )



    def _build_comparison_queries(self, query: str, ents: dict, llm: dict) -> list[dict]:
        """
        Build one search query per brand for comparison.

        Brand sources (merged in priority order):
          1. NLU ents['brands']          — regex-extracted from query
          2. LLM 'items' list            — LLM-extracted brand names (handles typos)
          3. Substring scan of raw query — catches brands even around typos

        LLM search_queries are intentionally NOT used here — they often miss one brand.
        """
        brands = list(ents.get('brands', []))  # NLU brands first

        # Source 2: LLM items (handles user typos like "comapre dell")
        for item in (llm.get('items') or []):
            item_clean = item.strip()
            if not item_clean:
                continue
            item_lower = item_clean.lower()
            matched_display = None
            for b_lower, b_display in KNOWN_BRANDS.items():
                if b_lower == item_lower or b_lower in item_lower or item_lower in b_lower:
                    matched_display = b_display
                    break
            candidate = matched_display or item_clean.title()
            if candidate not in brands:
                brands.append(candidate)

        # Source 3: substring scan of raw query (catches brands NLU missed due to typos)
        q_lower = query.lower()
        for b_lower, b_display in KNOWN_BRANDS.items():
            # Use substring match (not word-boundary) to handle typo adjacency
            if b_lower in q_lower and b_display not in brands:
                brands.append(b_display)

        # Deduplicate while preserving order, limit to first 4
        seen = set()
        unique_brands = []
        for b in brands:
            key = b.lower()
            if key not in seen:
                seen.add(key)
                unique_brands.append(b)
        brands = unique_brands[:4]

        # Update ents with merged brand list
        if brands:
            ents['brands'] = brands

        # Determine the product type by stripping brand names + comparison filler words
        product_type = q_lower
        for b in brands:
            product_type = re.sub(r'\b' + re.escape(b.lower()) + r'\b', '', product_type)
        product_type = re.sub(
            r'\b(?:vs\.?|versus|compare|comparison|difference\s+between|'
            r'just|only|which\s+is\s+better|better\s+than|between|and|or|'
            r'tell|me|show|find)\b',
            '', product_type, flags=re.I)
        # Strip leading "for" but preserve "for gaming", "for music" etc.
        product_type = re.sub(r'^\s*for\s+', '', product_type.strip())
        product_type = re.sub(r'\s+', ' ', product_type).strip()

        # Deduplicate repeated words (e.g. "phones phones" -> "phones")
        seen_words: set = set()
        deduped_words = []
        for w in product_type.split():
            if w not in seen_words:
                seen_words.add(w)
                deduped_words.append(w)
        product_type = ' '.join(deduped_words).strip()

        # Fallback to audio_type or dept if product_type is too short
        audio_t = ents.get('audio_type', '')
        dept    = ents.get('dept', '')
        if not product_type or len(product_type) < 3:
            product_type = audio_t or dept or 'product'

        price_s = f"under ₹{ents['max_price']:,}" if ents.get('max_price') else ''

        # Build one query per brand
        if len(brands) >= 2:
            queries = []
            for brand in brands:
                parts = ['best', brand, product_type]
                if price_s:
                    parts.append(price_s)
                parts.append('India')
                q_str = re.sub(r'\s+', ' ', ' '.join(filter(None, parts))).strip()
                queries.append({'label': brand, 'query': q_str})
            return queries

        # Single brand
        if len(brands) == 1:
            brand = brands[0]
            parts = [brand, product_type]
            if price_s:
                parts.append(price_s)
            parts.append('India')
            q_str = re.sub(r'\s+', ' ', ' '.join(filter(None, parts))).strip()
            return [{'label': brand, 'query': q_str}]

        # No brands detected at all — fall back to LLM search_queries
        llm_sq = llm.get('search_queries') or []
        if llm_sq:
            return [
                {'label': q.get('label', 'Results'), 'query': q.get('query', '')}
                for q in llm_sq if q.get('query')
            ]

        return [{'label': 'Comparison', 'query': query.strip() + ' India'}]

    def _apply_qu_to_ents(self, qu: QueryUnderstanding, ents: dict) -> None:
        """
        Merge QueryUnderstanding detections into NLU entities.
        QU is authoritative: it ran deterministically on the raw user query.
        Priority: explicit user text > QU > NLU > LLM.
        """
        # Audio type — QU is authoritative (deterministic regex on the original query)
        if qu.audio_type:
            _AUDIO_DEPT_MAP = {
                'earbuds':    'Earbuds',
                'earphones':  'Earphones',
                'headphones': 'Headphones',
                'neckband':   'Neckband',
                'speaker':    'Speakers',
            }
            ents['audio_type'] = qu.audio_type   # always enforce QU audio_type
            ents['dept'] = _AUDIO_DEPT_MAP.get(qu.audio_type, ents.get('dept'))
            print(f"[Bot] QU audio_type={qu.audio_type!r} applied to ents")
        elif qu.category:
            _GENERIC_DEPT_MAP = {
                'laptop':          ('Laptops', 'Electronics'),
                'phone':           ('Mobile Phones', 'Cell_Phones_and_Accessories'),
                'smartwatch':      ('Smartwatches', 'Electronics'),
                'shoes':           ('Footwear', 'Clothing_Shoes_and_Jewelry'),
                't-shirt':         ('T-Shirts', 'Clothing_Shoes_and_Jewelry'),
                'shirt':           ('Shirts', 'Clothing_Shoes_and_Jewelry'),
                'jeans':           ('Jeans', 'Clothing_Shoes_and_Jewelry'),
                'watch':           ('Watches', 'Clothing_Shoes_and_Jewelry'),
                'tablet':          ('Tablets', 'Electronics'),
                'camera':          ('Cameras', 'Electronics'),
                'refrigerator':    ('Refrigerators', 'Home_and_Kitchen'),
                'washing machine': ('Washing Machines', 'Home_and_Kitchen'),
                'air conditioner': ('Air Conditioners', 'Home_and_Kitchen'),
                'television':      ('Televisions', 'Electronics'),
                'bag':             ('Bags', 'Clothing_Shoes_and_Jewelry'),
            }
            if qu.category in _GENERIC_DEPT_MAP:
                dept, cat = _GENERIC_DEPT_MAP[qu.category]
                ents['dept'] = dept
                ents['category'] = cat

        # Brand — QU brand registry and fuzzy matching is authoritative
        if qu.brands:
            ents['brands'] = list(qu.brands)
            print(f"[Bot] QU brands={qu.brands!r} applied to ents")
        elif qu.brand:
            ents['brands'] = [qu.brand] if isinstance(qu.brand, str) else list(qu.brand)
            print(f"[Bot] QU brand={qu.brand!r} applied to ents")

        # Color
        if qu.color:
            ents['colors'] = [qu.color]

        # Price
        if qu.price.get('max'):
            ents['max_price'] = qu.price['max']
        if qu.price.get('min'):
            ents['min_price'] = qu.price['min']

        # Specs
        if qu.specifications:
            tech_specs = ents.setdefault('tech_specs', {})
            for spec, val in qu.specifications.items():
                tech_specs[spec] = val

        # Use-case (gaming, coding, music, etc.)
        if qu.use_case:
            ents['use_case'] = qu.use_case
            if qu.use_case == 'gaming':
                ents['gaming'] = True

        # Attach full QU and requirements for downstream strict validation
        ents['qu'] = qu
        ents['hard_requirements'] = qu.hard_requirements
        ents['soft_preferences'] = qu.soft_preferences
        ents['category_confidence'] = qu.category_confidence

    def _merge_llm_into_ents(self, ents: dict, llm: dict, queries: list) -> dict:
        """
        Merge LLM-extracted features into NLU entities.
        LLM values override NLU only when NLU didn't detect them.
        Count and audio type: LLM takes priority.
        """
        features = llm.get('features') or {}

        # Audio type — LLM fills ONLY when neither QU nor NLU detected anything
        # Priority: QU (explicit) > NLU (deterministic) > LLM (inference)
        llm_audio = features.get('audio_type')
        if llm_audio and not ents.get('audio_type'):
            ents['audio_type'] = llm_audio
            print(f"[Bot] LLM audio_type={llm_audio!r} applied (NLU+QU had None)")
        elif llm_audio and ents.get('audio_type') and llm_audio != ents['audio_type']:
            # LLM disagrees with NLU/QU — keep NLU/QU
            print(f"[Bot] LLM audio_type={llm_audio!r} IGNORED — NLU/QU has {ents['audio_type']!r}")

        # Count — LLM takes priority
        llm_count = llm.get('count')
        if llm_count and isinstance(llm_count, int) and llm_count > 0:
            ents['count'] = llm_count

        # Tech specs from LLM
        if not ents.get('tech_specs'):
            ents['tech_specs'] = {}
        for spec in ('processor', 'ram', 'storage', 'display', 'camera', 'battery'):
            if features.get(spec) and not ents['tech_specs'].get(spec):
                ents['tech_specs'][spec] = features[spec]

        # Fashion style / fit
        for key in ('style', 'fit'):
            val = features.get(key)
            if val and val not in ents.get('fashion_styles', []):
                ents.setdefault('fashion_styles', []).append(val)

        # Material / fabric
        val = features.get('fabric')
        if val and val not in ents.get('materials', []):
            ents.setdefault('materials', []).append(val)

        # Vague expansions
        vague_expansions = llm.get('vague_expansions') or []
        if vague_expansions:
            existing = ents.get('vague_hint', '')
            extra    = ' '.join(vague_expansions)
            ents['vague_hint'] = (existing + ' ' + extra).strip()

        # Sync dept with audio_type
        if ents.get('audio_type'):
            _AUDIO_DEPT_MAP = {
                'earbuds':    'Earbuds',
                'earphones':  'Earphones',
                'headphones': 'Headphones',
                'neckband':   'Neckband',
                'speaker':    'Speakers',
            }
            ents['dept'] = _AUDIO_DEPT_MAP.get(ents['audio_type'], ents.get('dept'))

        return ents

    def _query_has_brands(self, q: str) -> bool:
        """Quick check: does the query mention any known brand name?"""
        ql = q.lower()
        return any(b_lower in ql for b_lower in KNOWN_BRANDS)

    def _enrich(self, q: str) -> str:
        words = q.split()
        if len(words) <= 4 and self.history:
            # Only enrich if this is a follow-up modifier, not a new topic.
            # If the short query already has a category/dept or brand, treat as standalone.
            try:
                from src.nlu_engine import analyse
                new_nlu = analyse(q)
                new_ents = new_nlu.get('entities', {})
                if new_ents.get('dept') or new_ents.get('category') or new_ents.get('brands') or new_ents.get('audio_type'):
                    return q
            except Exception as e:
                print(f"[Bot] NLU pre-analysis in _enrich failed: {e}")

            prev_user = next(
                (h['content'] for h in reversed(self.history) if h['role'] == 'user'),
                None)
            if prev_user:
                return f"{prev_user} {q}"
        return q


    def _push(self, role: str, content: str, intent: str = '', entities: dict = None):
        self.history.append({
            'role':     role,
            'content':  content,
            'intent':   intent,
            'entities': entities or {},
        })
        if len(self.history) > self.MAX_HISTORY * 2:
            self.history = self.history[-(self.MAX_HISTORY * 2):]

    def _empty(self) -> dict:
        return {
            'answer':   "Please type a product query!",
            'intent':   'empty',
            'entities': {},
            'products': [],
        }


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    bot = ShopBot()
    print("ShopBot India (India) (type 'exit' to quit)\n")
    print("Try:")
    print("  just compare dell and hp laptop for gaming")
    print("  which phone has better camera between realme and vivo")
    print("  compare samsung vs apple phone")
    print("  Best gaming laptop under ₹70000")
    print("  suggest 2 phones under 15000")
    print("  boAt earbuds under 2000")
    print("  JBL headphones under 3000")
    print("  printed cotton t shirt men under 500")
    print("  HP laptop i7 16GB RAM under 80000\n")

    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in ('exit', 'quit'):
            break
        if not msg:
            continue
        r = bot.chat(msg)
        print(f"\n[Bot] [{r['intent']}] {r['answer']}\n")
        for i, p in enumerate(r['products'], 1):
            print(f"  {i}. {p['title']} - {p['price_inr']}")
            print(f"     Link: {p['link']}")
        print()