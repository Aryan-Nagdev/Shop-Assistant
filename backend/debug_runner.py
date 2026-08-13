import os
import sys

# Ensure stdout handles utf-8 encoding safely on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chatbot import ShopBot

bot = ShopBot()
q = 'suggest earbuds under 1k'
print("=" * 80)
print(f"RUNNING BOT.CHAT('{q}')")
print("=" * 80)

res = bot.chat(q)

print("\n--- RESULTS ---")
print("INTENT:", res['intent'])
print(f"ANSWER:\n{res['answer']}\n")
print(f"PRODUCTS RETURNED: {len(res['products'])}")
for idx, p in enumerate(res['products'], 1):
    alt = f" [ALT: {p.get('alternative_diff')}]" if p.get('is_alternative') else ""
    print(f"  {idx}. {p.get('title')} | {p.get('price_inr')} | brand={p.get('brand')}{alt}")
