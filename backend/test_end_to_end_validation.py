"""
test_end_to_end_validation.py  –  Comprehensive 9-Test End-to-End Verification Suite
───────────────────────────────────────────────────────────────────────────────────
Verifies all 9 mandatory user tests:
  Test 1: suggest earbuds under 1k
  Test 2: best earbuds under 500
  Test 3: u s polo shoes under 2k
  Test 4: blue u s polo shoes under 3k
  Test 5: i5 16GB 512GB laptop under 50k
  Test 6: i5 laptop with graphics under 30k
  Test 7: gud eardbuds under 2k (typo)
  Test 8: blu shoes (colour typo)
  Test 9: samsng phone (brand typo)
"""
from __future__ import annotations
import sys
import os

# Ensure stdout handles utf-8 encoding safely on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chatbot import ShopBot


def run_tests():
    bot = ShopBot()

    test_queries = [
        ("TEST 1: suggest earbuds under 1k", "suggest earbuds under 1k"),
        ("TEST 2: best earbuds under 500", "best earbuds under 500"),
        ("TEST 3: u s polo shoes under 2k", "u s polo shoes under 2k"),
        ("TEST 4: blue u s polo shoes under 3k", "blue u s polo shoes under 3k"),
        ("TEST 5: i5 16GB 512GB laptop under 50k", "i5 16GB 512GB laptop under 50k"),
        ("TEST 6: i5 laptop with graphics under 30k", "i5 laptop with graphics under 30k"),
        ("TEST 7 (Typo): gud eardbuds under 2k", "gud eardbuds under 2k"),
        ("TEST 8 (Colour typo): blu shoes", "blu shoes"),
        ("TEST 9 (Brand typo): samsng phone", "samsng phone"),
    ]

    for label, query in test_queries:
        print("=" * 80)
        print(f"RUNNING: {label}")
        print("=" * 80)
        bot.clear()
        res = bot.chat(query)
        print(f"Answer Summary: {res['answer'][:160]}...")
        print(f"Products Returned ({len(res['products'])}):")
        for idx, p in enumerate(res['products'][:4], 1):
            alt_tag = f" [ALT: {p.get('alternative_diff')}]" if p.get('is_alternative') else ""
            print(f"  {idx}. {p['title']} | {p['price_inr']} | brand={p.get('brand')}{alt_tag}")
        print()


if __name__ == '__main__':
    run_tests()
