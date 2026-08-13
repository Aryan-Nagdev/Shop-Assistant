"""
test_chat_e2e.py - End-to-end test of ShopBot.chat() across diverse queries
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot import ShopBot

def test_e2e():
    bot = ShopBot()

    queries = [
        "compare nike and adidas",
        "which laptop is best hp or dell",
        "which laptop is best for college work",
    ]

    for q in queries:
        print(f"\n========================================\nTesting: '{q}'\n========================================", flush=True)
        res = bot.chat(q)
        print(f"Intent resolved: {res.get('intent')}", flush=True)
        print(f"Search required: {res.get('search_required')}", flush=True)
        print(f"Products returned count: {len(res.get('products', []))}", flush=True)
        print(f"Response text sample: {res.get('answer', '')[:120]}...", flush=True)
        assert res.get('answer'), f"No text answer returned for {q}"

    print("\n✅ END-TO-END CHAT TESTS COMPLETED SUCCESSFULLY!", flush=True)

if __name__ == "__main__":
    test_e2e()
