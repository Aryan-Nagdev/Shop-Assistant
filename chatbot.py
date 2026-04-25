"""
chatbot.py – Session-aware orchestrator
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.nlu_engine import analyse
from src.live_search import fetch_one, fetch_comparison
from src.response_builder import build_response


class ShopBot:
    """Per-session India e-commerce chatbot."""

    MAX_HISTORY   = 10
    CONTEXT_TURNS = 3

    def __init__(self):
        self.history: list[dict] = []

    # ── Public ─────────────────────────────────────────────────────────────────
    def chat(self, user_msg: str) -> dict:
        user_msg = user_msg.strip()
        if not user_msg:
            return self._empty()

        # Enrich short follow-ups with recent context
        effective_q = self._enrich(user_msg)

        # 1. NLU
        nlu     = analyse(effective_q)
        intent  = nlu['intent']
        ents    = nlu['entities']
        queries = nlu['queries']

        print(f"[Bot] intent={intent} | queries={[q['query'] for q in queries]}")

        # 2. Live search
        products    = []
        brands_data = None

        if intent == 'info_only':
            pass   # no search needed

        elif intent == 'comparison':
            brands_data = fetch_comparison(queries, ents, per_brand=3)
            for prods in brands_data.values():
                products.extend(prods)

        elif intent == 'single_best':
            prods    = fetch_one(queries[0]['query'] if queries else effective_q, ents, top_n=3)
            products = prods[:1]

        else:
            if queries:
                products = fetch_one(queries[0]['query'], ents, top_n=6)

        # 3. Build response
        text, cards = build_response(intent, ents, user_msg, products, brands_data)

        # 4. Update history
        self._push('user',      user_msg, intent, ents)
        self._push('assistant', text,     intent, {})

        return {
            'answer':   text,
            'intent':   intent,
            'entities': ents,
            'products': cards,
        }

    def clear(self):
        self.history.clear()

    # ── Private ────────────────────────────────────────────────────────────────
    def _enrich(self, q: str) -> str:
        """
        If the new message is a short follow-up (≤ 4 words),
        prepend the last user message for context.
        e.g. User: "best gaming laptop" → "under 60000"
             becomes: "best gaming laptop under 60000"
        """
        words = q.split()
        if len(words) <= 4 and self.history:
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
    print("ShopBot India 🇮🇳 (type 'exit' to quit)\n")
    print("Try:")
    print("  Realme vs Vivo gaming phone")
    print("  Suggest 1 best gaming phone")
    print("  Jeans for a blue t-shirt men")
    print("  How to clean leather shoes\n")

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
        print(f"\n🤖 {r['answer']}\n")
        for i, p in enumerate(r['products'], 1):
            print(f"  {i}. {p['title']} — {p['price_inr']}")
            print(f"     🔗 {p['link']}")
        print()
