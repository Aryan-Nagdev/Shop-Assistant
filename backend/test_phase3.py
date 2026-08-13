"""
test_phase3.py  –  Phase 3 Smart Alternatives & Conversational Shopping Test Suite
─────────────────────────────────────────────────────────────────────────────────
Tests all 5 required Phase 3 scenarios:
  Scenario 1: Impossible budget audio (best earbuds under 500)
  Scenario 2: Impossible budget laptop (i5 16GB 512 SSD laptop with graphics under 30k)
  Scenario 3: Tight budget brand/color (u s polo ass blue shoes under 2000)
  Scenario 4: Qualitative & spec combined query (best laptoop for coding with gud battery under 50k)
  Scenario 5: Multi-turn conversational sequence (5 consecutive turns verifying slot preservation & updates)
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


def run_phase3_suite():
    bot = ShopBot()

    print("=" * 85)
    print("PHASE 3: SMART ALTERNATIVES AND CONVERSATIONAL SHOPPING TEST SUITE")
    print("=" * 85 + "\n")

    # ── SCENARIO 1: Impossible Budget Audio ───────────────────────────────────
    print("━" * 85)
    print("SCENARIO 1: 'best earbuds under 500'")
    print("━" * 85)
    res1 = bot.chat("best earbuds under 500")
    print(f"Assistant Response:\n{res1['answer']}\n")
    print(f"Products Count: {len(res1['products'])}")
    for idx, p in enumerate(res1['products'], 1):
        alt_tag = f" [ALTERNATIVE: {p.get('alternative_diff', '')}]" if p.get('is_alternative') else ""
        print(f"  {idx}. {p['title']} | {p['price_inr']}{alt_tag}")
    print()

    # ── SCENARIO 2: Impossible Budget Gaming Laptop ───────────────────────────
    print("━" * 85)
    print("SCENARIO 2: 'i5 16GB 512 SSD laptop with graphics under 30k'")
    print("━" * 85)
    bot.clear()
    res2 = bot.chat("i5 16GB 512 SSD laptop with graphics under 30k")
    print(f"Assistant Response:\n{res2['answer']}\n")
    print(f"Products Count: {len(res2['products'])}")
    for idx, p in enumerate(res2['products'], 1):
        alt_tag = f" [ALTERNATIVE: {p.get('alternative_diff', '')}]" if p.get('is_alternative') else ""
        print(f"  {idx}. {p['title']} | {p['price_inr']}{alt_tag}")
    print()

    # ── SCENARIO 3: Tight Budget Brand & Color Shoes ──────────────────────────
    print("━" * 85)
    print("SCENARIO 3: 'u s polo ass blue shoes under 2000'")
    print("━" * 85)
    bot.clear()
    res3 = bot.chat("u s polo ass blue shoes under 2000")
    print(f"Assistant Response:\n{res3['answer']}\n")
    print(f"Products Count: {len(res3['products'])}")
    for idx, p in enumerate(res3['products'], 1):
        alt_tag = f" [ALTERNATIVE: {p.get('alternative_diff', '')}]" if p.get('is_alternative') else ""
        print(f"  {idx}. {p['title']} | {p['price_inr']}{alt_tag}")
    print()

    # ── SCENARIO 4: Coding + Good Battery Laptop under 50k ────────────────────
    print("━" * 85)
    print("SCENARIO 4: 'best laptoop for coding with gud battery under 50k'")
    print("━" * 85)
    bot.clear()
    res4 = bot.chat("best laptoop for coding with gud battery under 50k")
    print(f"Assistant Response:\n{res4['answer']}\n")
    print(f"Products Count: {len(res4['products'])}")
    for idx, p in enumerate(res4['products'], 1):
        print(f"  {idx}. {p['title']} | {p['price_inr']}")
    print()

    # ── SCENARIO 5: Conversational Multi-Turn Sequence ─────────────────────────
    print("━" * 85)
    print("SCENARIO 5: CONVERSATIONAL MULTI-TURN SEQUENCE")
    print("━" * 85)
    bot.clear()

    turns = [
        "i5 laptop under 50k",
        "make it 60k",
        "only 16GB",
        "black colour",
        "forget the i5 requirement",
    ]

    for turn_idx, user_turn in enumerate(turns, 1):
        print(f"Turn {turn_idx} -> User: '{user_turn}'")
        res = bot.chat(user_turn)
        ctx = bot.conversation_mgr.context
        print(f"  Active Slots : category={ctx.category!r}, brand={ctx.brand!r}, price_max={ctx.max_price}, color={ctx.color!r}, specs={ctx.specifications}")
        print(f"  Synthesized  : '{ctx.synthesize_effective_query()}'")
        print(f"  Answer       : {res['answer'][:120]}...")
        print(f"  Products     : {len(res['products'])} products returned")
        if res['products']:
            print(f"  Top Product  : {res['products'][0]['title']} ({res['products'][0]['price_inr']})")
        print()


if __name__ == '__main__':
    run_phase3_suite()
