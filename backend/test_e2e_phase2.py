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
queries = [
    'earbuds under 2000',
    'headphones under 2000',
    'u s polo shoes',
    'blue u s polo shoes under 3000',
    'i5 16GB laptop under 50000',
    'gaming laptop with graphics under 30000',
]

for q in queries:
    print('=' * 75)
    print('USER QUERY:', q)
    print('=' * 75)
    res = bot.chat(q)
    print('INTENT :', res['intent'])
    print('ANSWER :', res['answer'][:180] + ('...' if len(res['answer']) > 180 else ''))
    print(f"PRODUCTS RETURNED: {len(res['products'])}")
    for idx, p in enumerate(res['products'][:3], 1):
        print(f"  {idx}. {p.get('title')} | {p.get('price_inr')} | brand={p.get('brand')}")
    print()
