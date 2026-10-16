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
import sys, os, re, random
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

# Explicit single product request detector (user clearly wants exactly one best choice)
_SINGLE_PRODUCT_RE = re.compile(
    r'\b(?:1|one)\s+(?:best|top|option|product|choice|recommendation|pick)\b'
    r'|\b(?:suggest|recommend|give|show|find|pick)\s+(?:me\s+)?(?:just\s+|only\s+)?(?:1|one)\b'
    r'|\b(?:only|just)\s+(?:1|one)\b'
    r'|\brecommend\s+(?:me\s+)?(?:1|one)\b'
    r'|\b(?:give\s+me|find\s+me|show\s+me|tell\s+me|what\s+is|what\'s)\s+(?:the\s+)?(?:single\s+best|absolute\s+best|#1|number\s+one)\b'
    r'|\b(?:give\s+me|what\s+is|what\'s)\s+the\s+best\s+(?:\w+\s+)?(?:under|below|for|in)?\b'
    r'|\bthe\s+(?:single\s+best|only\s+one|best\s+one)\b'
    r'|\bwhich\s+one\s+(?:should\s+i|to|shall\s+i)?\s*(?:buy|choose|pick|get)\b'
    r'|\bwhich\s+one\s+(?:is\s+best|is\s+better|do\s+you\s+recommend)\b'
    r'|\bpick\s+(?:the\s+best\s+one|one)\s+for\s+me\b'
    r'|\bwhich\s+is\s+the\s+best\s+one\b'
    r'|\b(?:ek\s+hi|ek\s+best|sirf\s+ek|kaunsa\s+ek)\b',
    re.I
)


class ShopBot:
    """Per-session India e-commerce chatbot."""

    MAX_HISTORY   = 10
    CONTEXT_TURNS = 3

    def __init__(self):
        self.history: list[dict] = []
        self.conversation_mgr = ConversationManager()
        self.last_products: list[dict] = []

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

        shown_answer = self._try_answer_about_shown_products(user_msg, effective_lang)
        if shown_answer is not None:
            return shown_answer

        if effective_q == qu_input and getattr(qu, 'normalized_query', None):
            search_query_seed = qu.normalized_query
        else:
            search_query_seed = effective_q

        # ── Clarification gate ─────────────────────────────────────────────────
        llm = None
        if qu.needs_clarification and context.is_empty():
            llm_check = llm_reason(effective_q, language=effective_lang)
            llm_intent = llm_check.get('canonical_intent') or llm_check.get('intent')
            llm_conf = llm_check.get('confidence', 0.0)
            llm_has_items = bool(llm_check.get('items')) or bool(llm_check.get('search_queries'))
            llm_expl = llm_check.get('explanation', '')

            # If LLM understands the query as a valid shopping or information intent, recover it
            if (llm_intent in ('information', 'comparison', 'recommendation', 'product_search', 'multi_item')
                    and (llm_conf >= 0.55 or llm_has_items or (llm_intent == 'information' and len(llm_expl) > 25))):
                print(f"[Bot] LLM recovered vague QU clarification into valid intent={llm_intent!r} (conf={llm_conf:.2f})")
                qu.needs_clarification = False
                llm = llm_check
            else:
                print(f"[Bot] Query genuinely unresolvable / vague — returning clarification fallback.")
                clar_msg = qu.clarification_msg or "What type of product are you looking for? For example: laptop, phone, earbuds, shoes, t-shirt, or something else?"
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

        # Skip the Groq understanding call for already-clear shopping queries
        if llm is None:
            qu_ready = (
                not qu.needs_clarification
                and qu.intent in ('recommendation', 'product_search', 'comparison', 'information')
                and (
                    qu.category 
                    or qu.audio_type 
                    or (qu.intent == 'comparison' and len(qu.brands or []) >= 2)
                    or (qu.intent == 'information' and not qu.search_required)
                )
            )
            if qu_ready:
                print(f"[Bot] Skipping LLM reason — query intent '{qu.intent}' already understood by QU.")
                llm = {
                    'intent': qu.intent,
                    'canonical_intent': qu.intent,
                    'search_required': qu.search_required if qu.intent != 'comparison' else True,
                    'explanation': '',
                    'items': qu.brands or [],
                    'count': None,
                    'features': {},
                    'vague_expansions': [],
                    'search_queries': [],
                    'confidence': 0.92,
                }
            else:
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

        # Rebuild search strings after QU/LLM slots are merged (gender, fabric, use-case)
        from src.nlu_engine import build_search_queries
        rebuilt = build_search_queries(search_query_seed, nlu.get('intent', 'product_search'), ents)
        if rebuilt:
            queries = rebuilt

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
                is_single = self._is_single_product_intent(user_msg, ents, nlu, llm)
                nlu_intent_raw = nlu.get('intent', '')

                if is_single or nlu_intent_raw == 'single_best':
                    prods    = fetch_one(queries[0]['query'] if queries else search_query_seed, ents, top_n=3)
                    products = prods[:1]
                    intent   = 'single_best'
                elif intent == 'multi_item' and nlu_intent_raw == 'multi_item':
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
                    target_count = ents.get('count')
                    if not target_count or not isinstance(target_count, int) or target_count <= 0:
                        target_count = DEFAULT_COUNT
                    if queries:
                        products = fetch_one(queries[0]['query'], ents, top_n=target_count)
                    else:
                        products = fetch_one(search_query_seed, ents, top_n=target_count)

            else:
                target_count = ents.get('count')
                if not target_count or not isinstance(target_count, int) or target_count <= 0:
                    target_count = DEFAULT_COUNT
                q_str = queries[0]['query'] if queries else search_query_seed
                products = fetch_one(q_str, ents, top_n=target_count)

            # ── STEP 4: Build response ─────────────────────────────────────────
            text, cards = build_response(
                intent, ents, user_msg, products, brands_data,
                llm_explanation=explanation,
                language=effective_lang,
            )

        # ── Strip any residual markdown ** bold from final response ───────────
        if text:
            text = re.sub(r'\*\*(.*?)\*\*', r'\1', text).replace('**', '')

        # ── STEP 5: Update history ─────────────────────────────────────────────
        self._push('user',      user_msg, intent, ents)
        self._push('assistant', text,     intent, {})

        # ── Persist last shown products for material / which-one follow-ups ──
        if cards:
            self.last_products = list(cards)
            self.conversation_mgr.context.last_products = list(cards)
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
        self.last_products = []

    def _is_single_product_intent(
        self, user_msg: str, ents: dict, nlu: dict, llm: dict
    ) -> bool:
        """
        Determines whether the user clearly requested ONE specific product/choice
        or is asking for recommendations/options where multiple products should be returned.
        """
        msg = (user_msg or '').strip()
        if not msg:
            return False

        # 1. Regex check for explicit single request (e.g. "give me the best laptop", "which one to buy", "recommend 1")
        if _SINGLE_PRODUCT_RE.search(msg):
            return True

        # 2. NLU detected single_best
        if nlu.get('intent') == 'single_best':
            return True

        # 3. Explicit count of 1 in entities only if explicitly stated by user
        count = ents.get('count')
        if count == 1 and bool(re.search(r'\b(?:1|one|only\s+one|just\s+one|single)\b', msg, re.I)):
            return True

        return False

    _SHOWN_PRODUCT_RE = re.compile(
        r'\b(?:which\s+one|which\s+product|this\s+(?:one|shoe|product|shirt|item)|'
        r'these\s+(?:ones|products|shoes)|the\s+(?:first|second|third)\s+one|'
        r'better\s+for|is\s+this\s+cotton|made\s+of|material|fabric|upper\s+material|'
        r'tell\s+me\s+about\s+(?:the\s+)?material|better\s+material|abs\s+plastic|aluminum|what\s+this\s+means)\b',
        re.I,
    )
    _MATERIAL_Q_RE = re.compile(
        r'\b(?:material|fabric|made\s+of|cotton|upper\s+material|build|abs\s+plastic|aluminum|aluminium|what\s+this\s+means)\b',
        re.I,
    )

    def _try_answer_about_shown_products(self, user_msg: str, language: str) -> dict | None:
        """Answer follow-ups about currently displayed product cards or material questions without a new live search."""
        products = self.last_products or self.conversation_mgr.context.last_products
        is_material = bool(self._MATERIAL_Q_RE.search(user_msg))

        # Check if query is an explanation about ABS Plastic / Aluminum or other materials
        q_lower = user_msg.lower()
        if is_material and re.search(r'\b(?:abs\s+plastic|aluminum|aluminium|what\s+this\s+means|properties\s+of)\b', q_lower):
            text = self._answer_material_question(user_msg, products or [])
            intent = 'information'
            text = re.sub(r'\*\*(.*?)\*\*', r'\1', text).replace('**', '')
            self._push('user', user_msg, intent, {})
            self._push('assistant', text, intent, {})
            self.conversation_mgr.context.last_intent = intent
            return {
                'answer':          text,
                'intent':          intent,
                'search_required': False,
                'entities':        {},
                'products':        products or [],
                'language':        language,
            }

        # If user asks about "this shoe" / "this product" / "made of" but no cards are currently displayed
        if not products and is_material and re.search(r'\b(?:this|these|the)\s+(?:one|shoe|shirt|product|item|ones|shoes|shirts|products|items)\b|\bwhat\s+material\s+is\s+this\b|\bwhat\s+is\s+this\s+made\s+of\b', q_lower):
            text = "There are no products currently shown on your screen to inspect. Please search for a product or category first (e.g. running shoes or formal blazers), and I will gladly provide its material and build details."
            intent = 'information'
            self._push('user', user_msg, intent, {})
            self._push('assistant', text, intent, {})
            self.conversation_mgr.context.last_intent = intent
            return {
                'answer':          text,
                'intent':          intent,
                'search_required': False,
                'entities':        {},
                'products':        [],
                'language':        language,
            }

        if not products or not self._SHOWN_PRODUCT_RE.search(user_msg):
            return None

        if is_material:
            text = self._answer_material_question(user_msg, products)
        else:
            text = self._answer_which_shown_product(user_msg, products)

        intent = 'information'
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text).replace('**', '')
        self._push('user', user_msg, intent, {})
        self._push('assistant', text, intent, {})
        self.conversation_mgr.context.last_intent = intent
        return {
            'answer':          text,
            'intent':          intent,
            'search_required': False,
            'entities':        {},
            'products':        products,
            'language':        language,
        }

    def _product_material_rows(self, product: dict) -> list[dict]:
        from src.material_analyzer import get_card_materials
        return get_card_materials(
            title=product.get('title') or '',
            category=product.get('category'),
            brand=product.get('brand'),
            description=product.get('description') or '',
        )

    def _format_material_rows(self, rows: list[dict], limit: int = 4) -> str:
        bits = []
        for row in rows[:limit]:
            part = (row.get('part') or 'Part').strip()
            mat = (row.get('material') or '').strip()
            if mat:
                bits.append(f"{part}: {mat}")
        return '; '.join(bits)

    def _answer_material_question(self, user_msg: str, products: list[dict]) -> str:
        q = user_msg.lower()

        # Material explanation questions (e.g. ABS plastic, aluminum, blazer context)
        if re.search(r'\b(?:abs\s+plastic|aluminum|aluminium)\b', q) or re.search(r'\bwhat\s+this\s+means\b', q):
            return (
                "ABS plastic (Acrylonitrile Butadiene Styrene) is a rigid, impact-resistant thermoplastic polymer known for its lightweight strength, durability, and resistance to scratches and drops. "
                "Aluminum is a lightweight, corrosion-resistant metal that provides high structural rigidity, sleek aesthetics, and excellent heat dissipation. "
                "When used for the main body of a product, this combination provides a tough, impact-absorbing outer shell with rigid structural reinforcement. "
                "If this specification appears under an apparel listing such as a formal blazer, it typically refers to structural hardware (such as buttons, zippers, or internal garment stays) or is an e-commerce catalog specification error, as blazers are primarily constructed from fabrics like cotton, polyester, rayon, or wool blends."
            )

        asking_compare = bool(re.search(r'\b(?:which|better|compare)\b', q))
        asking_cotton = bool(re.search(r'\bcotton\b', q))
        asking_upper = bool(re.search(r'\bupper\b', q))

        if asking_compare and len(products) >= 2:
            lines = ["Here is the material information from the products on your cards:"]
            for i, p in enumerate(products[:4], 1):
                rows = self._product_material_rows(p)
                detail = self._format_material_rows(rows) or "no material details listed on the card"
                lines.append(f"{i}. {p.get('title', 'Product')} — {detail}.")
            lines.append("I am only using the material information already available for these listings, not extra guesses.")
            return ' '.join(lines)

        target = products[0] if products else {}
        if re.search(r'\bsecond\b', q) and len(products) > 1:
            target = products[1]
        elif re.search(r'\bthird\b', q) and len(products) > 2:
            target = products[2]
        else:
            # Check if user mentioned product title words in query
            for p in products:
                title_words = [w for w in (p.get('title') or '').lower().split() if len(w) > 3]
                if any(w in q for w in title_words[:4]):
                    target = p
                    break

        if not target:
            return "No matching product card is currently available to inspect material details."

        rows = self._product_material_rows(target)
        title = target.get('title') or 'This product'
        if asking_cotton:
            blob = ' '.join(
                f"{r.get('part','')} {r.get('material','')} {r.get('description','')}"
                for r in rows
            ).lower() + ' ' + title.lower()
            if 'cotton' in blob:
                return f"Yes — {title} lists cotton in its material information ({self._format_material_rows(rows) or 'cotton mentioned in the listing'})."
            return (
                f"The card for {title} does not confirm cotton. "
                f"Available material info: {self._format_material_rows(rows) or 'none listed on the card'}."
            )

        if asking_upper:
            upper = next((r for r in rows if 'upper' in (r.get('part') or '').lower()), None)
            if upper:
                return f"The upper on {title} is listed as {upper.get('material')}."
            titled = [r for r in rows if r.get('source') == 'title']
            if titled:
                return f"The listing for {title} mentions {self._format_material_rows(titled)}, but does not name a separate upper material."
            return f"No separate upper material is listed for {title}. Available: {self._format_material_rows(rows) or 'none on the card'}."

        if not rows:
            return f"I don't have material & build details on the card for {title}, so I won't invent them."
        return f"{title} — {self._format_material_rows(rows)}."

    def _answer_which_shown_product(self, user_msg: str, products: list[dict]) -> str:
        q = user_msg.lower()
        use = None
        if re.search(r'\brun(?:ning)?\b', q):
            use = 'running'
        elif re.search(r'\boffice|work|formal\b', q):
            use = 'office'
        elif re.search(r'\bcollege|campus|school\b', q):
            use = 'college'

        scored = []
        for p in products:
            title = (p.get('title') or '').lower()
            score = float(p.get('rating') or 0)
            if use == 'running' and re.search(r'\brun|sport|mesh|sneaker|trainer\b', title):
                score += 2
            if use == 'office' and re.search(r'\bformal|office|trouser|chino|shirt\b', title):
                score += 2
            if use == 'college' and re.search(r'\bcasual|backpack|sneaker|hoodie\b', title):
                score += 2
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        others = ', '.join(p.get('title', 'product') for _, p in scored[1:3]) if len(scored) > 1 else ''
        use_bit = f" for {use}" if use else ""
        extra = f" Compared with {others}." if others else ""
        return (
            f"Of the products currently shown, {best.get('title')} at {best.get('price_inr', '')} "
            f"is the better pick{use_bit}.{extra}"
        )

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
                # Guard: If query is actually asking for recommendations ("What are the best..."), it is NOT information
                if re.search(r'\b(?:what\s+(?:is|are)\s+(?:the\s+)?(?:best|top|recommended|good)|which\s+(?:is|are)\s+(?:the\s+)?(?:best|top))\b', user_msg, re.I):
                    brands = ents.get('brands', [])
                    if len(brands) >= 2:
                        print(f"[Bot] Overriding information -> comparison for best across {brands} (search_required=True)")
                        return 'comparison', True
                    print(f"[Bot] Overriding information -> recommendation for best product query (search_required=True)")
                    return 'recommendation', True

                print(f"[Bot] QU says information → no search.")
                return 'information', False

            if qu_intent == 'comparison':
                # Unless user explicitly requested no products / text-only, comparisons fetch real products
                if _NO_SEARCH_RE.search(user_msg):
                    print(f"[Bot] QU comparison with explicit no-search -> text only.")
                    return 'comparison', False
                print(f"[Bot] QU comparison -> search_required=True")
                return 'comparison', True

        # ── Priority 3: LLM when conf >= 0.65 ────────────────────────────────────
        if llm_canonical and conf >= 0.65:
            if llm_canonical == 'comparison':
                search_req = False if _NO_SEARCH_RE.search(user_msg) else True
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
        is_material_question = bool(re.search(
            r'\b(?:material|copper|brass|rivet|rivets|fabric|cotton|denim|leather|polyester|wool|nylon|linen|silk|'
            r'properties|benefits|tradeoffs?|durability|corrosion|hardware|zipper|stitching|build|finish)\b',
            query, re.I
        ))

        # LLM already provided an explanation via llm_reason — prefer it
        nudge_comparison = [
            "\n\n↪ *Want me to search for actual products with live ₹ prices? Just ask!*",
            "\n\n💡 *Curious about real deals? Let me know and I'll pull up live prices and top-rated models!*",
            "\n\n🔍 *Want to compare actual available products and latest discounts? Just say the word!*",
            "\n\n🛍️ *Ready to see specific models and live pricing in India? Ask anytime!*",
        ]
        nudge_info = [
            "\n\n↪ *Want me to find or compare actual products? Just ask!*",
            "\n\n💡 *Looking for concrete recommendations or live pricing? I'm ready to find them!*",
            "\n\n🔍 *If you'd like to check out actual models under a specific budget, let me know!*",
            "\n\n🛍️ *Feel free to ask for top-rated options or live deals anytime!*",
        ]

        if explanation and len(explanation) > 60:
            if is_material_question:
                return explanation
            nudge = random.choice(nudge_comparison) if intent == 'comparison' else random.choice(nudge_info)
            return explanation + nudge

        # Explanation was missing or too short — generate via inline Groq call
        try:
            import os
            from groq import Groq
            key = config.get_groq_api_key()
            if not key:
                raise ValueError("No API key")

            client = Groq(api_key=key)

            if intent == 'information':
                if is_material_question:
                    system_prompt = (
                        "You are an expert materials scientist and apparel/hardware engineer.\n"
                        "The user is asking about materials and components used in products.\n"
                        "Provide a thorough, fresh, direct, and well-structured explanation covering:\n"
                        "1. Key mechanical and chemical properties (e.g., tensile strength, ductility, corrosion resistance, patina).\n"
                        "2. Benefits and advantages of using this material in this product application.\n"
                        "3. Tradeoffs, limitations, or potential drawbacks (e.g., weight, cost, maintenance/oxidation).\n"
                        "Write naturally like modern AI. Do NOT recommend or sell products."
                    )
                    max_tok = 600
                else:
                    system_prompt = (
                        "You are a helpful India e-commerce and technology expert assistant.\n"
                        "Answer the user's question clearly, naturally, and concisely in 2-4 sentences.\n"
                        "Provide engaging, fresh conversational phrasing like ChatGPT. Be direct and accurate. "
                        "Do NOT recommend or mention specific products unless asked."
                    )
                    max_tok = 350
                user_content = query

            else:  # comparison
                brands = ents.get('brands', [])
                dept = ents.get('dept') or ents.get('category') or 'products'

                system_prompt = (
                    "You are a knowledgeable India e-commerce shopping expert.\n"
                    "The user wants to compare options. Give a fresh, engaging, structured comparison like modern conversational AI.\n\n"
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

            # Dynamic temperature for fresh, varied answers every turn
            dyn_temp = round(random.uniform(0.70, 0.85), 2)
            ans = ""
            for model_cand in config.GROQ_MODELS:
                try:
                    resp = client.chat.completions.create(
                        model=model_cand,
                        messages=messages,
                        temperature=dyn_temp,
                        max_tokens=max_tok,
                        timeout=8.0,
                    )
                    content = (resp.choices[0].message.content or "").strip()
                    if content:
                        ans = content
                        break
                except Exception as ex_m:
                    print(f"[Bot] Model {model_cand} in _generate_text_answer failed: {ex_m}")
                    continue

            if ans:
                ans = re.sub(r'\*\*(.*?)\*\*', r'\1', ans).replace('**', '')
                if is_material_question:
                    return ans
                nudge = random.choice([
                    "\n\n↪ Want me to search for actual products with live ₹ prices? Just ask!",
                    "\n\n💡 Curious about real deals? Let me know and I'll pull up live prices and top-rated models!",
                    "\n\n🔍 Want to compare actual available products and latest discounts? Just say the word!",
                    "\n\n🛍️ Ready to see specific models and live pricing in India? Ask anytime!",
                ]) if intent == 'comparison' else random.choice([
                    "\n\n↪ Want me to find or compare actual products? Just ask!",
                    "\n\n💡 Looking for concrete recommendations or live pricing? I'm ready to find them!",
                    "\n\n🔍 If you'd like to check out actual models under a specific budget, let me know!",
                    "\n\n🛍️ Feel free to ask for top-rated options or live deals anytime!",
                ])
                return ans + nudge

        except Exception as e:
            print(f"[Bot] _generate_text_answer fallback LLM failed: {e}")

        # Hard fallback
        if intent == 'comparison':
            return (
                "Both are strong options depending on your specific needs. "
                "For a detailed comparison with live prices, try asking: "
                "\"Compare [Brand A] vs [Brand B] under ₹X\""
            )
        q_low = query.lower()
        if 'copper' in q_low or 'brass' in q_low or 'rivet' in q_low:
            return (
                "Copper and brass rivets are classic, durable hardware choices widely used in heavy-duty apparel, workwear, and cargo trousers to reinforce high-stress stress points (such as pocket corners and seam junctions).\n\n"
                "Key Properties & Benefits:\n"
                "- Exceptional Corrosion Resistance: Both copper and brass are non-ferrous and naturally immune to rusting from perspiration or repeated laundry cycles.\n"
                "- High Ductility & Strength: They can be securely peened and cold-formed without fracturing, providing permanent reinforcement that prevents heavy fabric seams from splitting.\n"
                "- Timeless Aesthetic: Over time, both metals develop a rich, vintage oxidation patina without deteriorating structurally.\n\n"
                "Tradeoffs & Drawbacks:\n"
                "- Weight & Cost: Copper and brass are denser and more expensive than stamped steel or zinc alloys.\n"
                "- Verdigris Oxidation: In hot, humid conditions, exposure to harsh alkaline detergents or moisture can create greenish surface patina if not thoroughly dried."
            )
        if 'abs' in q_low or 'plastic' in q_low or 'aluminum' in q_low or 'blazer' in q_low:
            return (
                "ABS plastic (Acrylonitrile Butadiene Styrene) is a rigid, impact-resistant thermoplastic polymer known for durability, lightness, and scratch resistance. "
                "Aluminum is a lightweight, corrosion-resistant metal that provides strong structural rigidity and sleek aesthetics. "
                "When used for the main body of a product, this combination delivers a sturdy, impact-absorbing outer shell with lightweight structural support. "
                "If this appears under a garment listing like a formal blazer, it typically refers to structural hardware (buttons, zippers, or frame) or is an e-commerce catalog error, as blazers are made from fabrics such as cotton, polyester, or wool blends."
            )
        return (
            "That's a great question! For specific product help, ask me to find, "
            "recommend, or compare — I'll pull live Indian store results with ₹ prices."
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

        # Source 3: regex scan of raw query (catches brands with word boundaries to avoid substring false positives)
        q_lower = query.lower()
        for b_lower, b_display in KNOWN_BRANDS.items():
            if len(b_lower) >= 2 and re.search(r'\b' + re.escape(b_lower) + r'\b', q_lower) and b_display not in brands:
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
            r'\b(?:what\s+(?:is|are)|which\s+(?:is|are)|the|best|top|suggest|recommend|'
            r'vs\.?|versus|compare|comparison|difference\s+between|'
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
                'office wear':     ('Office Wear', 'Clothing_Shoes_and_Jewelry'),
                'clothing':        ('Clothing', 'Clothing_Shoes_and_Jewelry'),
                'trouser':         ('Trousers', 'Clothing_Shoes_and_Jewelry'),
                'hoodie':          ('Sweatshirts', 'Clothing_Shoes_and_Jewelry'),
                'jacket':          ('Jackets', 'Clothing_Shoes_and_Jewelry'),
                'kurta':           ('Ethnic Wear', 'Clothing_Shoes_and_Jewelry'),
                'dress':           ('Dresses', 'Clothing_Shoes_and_Jewelry'),
            }
            if qu.category in _GENERIC_DEPT_MAP:
                dept, amazon_cat = _GENERIC_DEPT_MAP[qu.category]
                ents['dept'] = dept
                ents['amazon_category'] = amazon_cat
                ents['category'] = qu.category
                print(f"[Bot] QU category={qu.category!r} dept={dept!r} applied to ents")
            else:
                ents['category'] = qu.category

        # Gender — QU detection is authoritative
        if getattr(qu, 'gender', None):
            ents['gender'] = qu.gender
            print(f"[Bot] QU gender={qu.gender!r} applied to ents")

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
            if 'material' in qu.specifications:
                mats = ents.setdefault('materials', [])
                if qu.specifications['material'] not in mats:
                    mats.append(qu.specifications['material'])

        # Use-case (gaming, coding, music, etc.)
        if qu.use_case:
            ents['use_case'] = qu.use_case
            if qu.use_case == 'gaming':
                ents['gaming'] = True

        # Count — QU is authoritative if set
        if getattr(qu, 'count', None):
            ents['count'] = qu.count
            print(f"[Bot] QU count={qu.count!r} applied to ents")

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

        # Count — LLM count applied only when genuine (not stray 1 from 'a laptop')
        llm_count = llm.get('count')
        if llm_count and isinstance(llm_count, int) and llm_count > 1:
            ents['count'] = llm_count
        elif llm_count == 1:
            raw_q = ents.get('raw_query') or ''
            if self._is_single_product_intent(raw_q, ents, {}, llm):
                ents['count'] = 1
            else:
                ents['count'] = None

        # Tech specs from LLM — fill missing slots AND propagate to hard_requirements
        if not ents.get('tech_specs'):
            ents['tech_specs'] = {}
        hard_reqs = list(ents.get('hard_requirements') or [])
        existing_hard_keys = {h.split(':')[0].strip().lower() for h in hard_reqs}

        # LLM field name → internal spec key mapping
        _LLM_SPEC_MAP = {
            'processor': 'cpu',
            'ram':       'ram',
            'storage':   'storage',
            'display':   'display',
            'camera':    'camera',
            'battery':   'battery',
        }
        for llm_field, internal_key in _LLM_SPEC_MAP.items():
            llm_val = features.get(llm_field)
            if not llm_val:
                continue
            # Fill missing tech_spec slot (NLU/QU have higher priority)
            if not ents['tech_specs'].get(internal_key):
                ents['tech_specs'][internal_key] = llm_val
                print(f"[Bot] LLM spec {internal_key}={llm_val!r} applied to tech_specs")
            # Promote to hard_requirements so the validator enforces the constraint
            if internal_key not in existing_hard_keys:
                req_label = f"{internal_key}: {llm_val}"
                hard_reqs.append(req_label)
                existing_hard_keys.add(internal_key)
                print(f"[Bot] LLM spec promoted to hard_requirement: {req_label!r}")

        ents['hard_requirements'] = hard_reqs

        # Fashion style / fit
        for key in ('style', 'fit'):
            val = features.get(key)
            if val and val not in ents.get('fashion_styles', []):
                ents.setdefault('fashion_styles', []).append(val)

        # Material / fabric — add to materials list AND tech_specs for search query building
        fabric_val = features.get('fabric')
        if fabric_val:
            mats = ents.setdefault('materials', [])
            if fabric_val not in mats:
                mats.append(fabric_val)
                print(f"[Bot] LLM fabric={fabric_val!r} added to materials")
            # Also store in tech_specs so search queries include the material
            if not ents['tech_specs'].get('material'):
                ents['tech_specs']['material'] = fabric_val
                print(f"[Bot] LLM fabric={fabric_val!r} stored in tech_specs['material']")

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