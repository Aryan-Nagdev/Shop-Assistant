"""
test_intent_part2.py
Comprehensive verification script for Part 2: Intent-Based Response Handling.
Tests both standalone queries and multi-turn conversational follow-ups.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Patch live_search to track whether it was actually called
import src.live_search as _ls_module
_live_search_called = []
_orig_fetch_one      = _ls_module.fetch_one
_orig_fetch_cmp      = _ls_module.fetch_comparison

def _tracked_fetch_one(*args, **kwargs):
    _live_search_called.append('fetch_one')
    return [{'title': 'Mock Product', 'price_inr': '₹2,999', 'brand': 'MockBrand', 'category': 'MockCat', 'is_alternative': False}]

def _tracked_fetch_comparison(*args, **kwargs):
    _live_search_called.append('fetch_comparison')
    return {
        'BrandA': [{'title': 'Mock A', 'price_inr': '₹4,999', 'brand': 'BrandA', 'category': 'MockCat', 'is_alternative': False}],
        'BrandB': [{'title': 'Mock B', 'price_inr': '₹4,799', 'brand': 'BrandB', 'category': 'MockCat', 'is_alternative': False}],
    }

_ls_module.fetch_one        = _tracked_fetch_one
_ls_module.fetch_comparison = _tracked_fetch_comparison

from chatbot import ShopBot

# (query, allowed_intents, expected_search)
STANDALONE_TESTS = [
    # 1. Information queries -> NO live search
    ("What is ANC?",                                          ["information"],               False),
    ("Is OLED better than LCD?",                             ["information"],               False),
    ("What should I look for in a running shoe?",             ["information"],               False),
    ("Is Nike better for beginners?",                        ["information", "comparison"], False),

    # 2. Comparison queries -> NO live search (unless price/buy explicitly requested)
    ("Nike vs Adidas for running",                           ["comparison"],                False),
    ("iPhone vs Samsung",                                    ["comparison"],                False),
    ("AirPods vs Galaxy Buds",                               ["comparison"],                False),
    ("Just compare Nike and Adidas",                         ["comparison"],                False),
    ("Don't recommend, just compare boAt and JBL earbuds",  ["comparison"],                False),
    ("Compare Nike and Adidas shoes under 5000",             ["comparison"],                True),

    # 3. Recommendation queries -> YES live search
    ("Which running shoes are best?",                        ["recommendation"],            True),
    ("Suggest earbuds under 2k",                             ["recommendation"],            True),
    ("Best laptop for coding?",                              ["recommendation"],            True),
    ("Show me the best Nike running shoes",                  ["recommendation"],            True),

    # 4. Product Search queries -> YES live search
    ("Nike shoes under 3k",                                  ["product_search"],            True),
    ("i5 laptop 16GB under 50k",                             ["product_search"],            True),
    ("Samsung phone under 20k",                              ["product_search"],            True),
]

CONVERSATION_TESTS = [
    {
        "name": "Comparison Follow-Up Thread",
        "turns": [
            ("Nike or Adidas for running?", ["comparison"], False, False),
            ("Which one is better for beginners?", ["comparison", "information"], False, False),
        ]
    },
    {
        "name": "Budget Modification Follow-Up Thread",
        "turns": [
            ("Suggest i5 laptops under 50k", ["recommendation", "product_search"], True, True),
            ("What about 60k?", ["recommendation", "product_search"], True, True),
        ]
    }
]

PASS_SYMBOL = "[PASS]"
FAIL_SYMBOL = "[FAIL]"


def run_tests():
    bot = ShopBot()

    print("\n" + "="*95)
    print("PART 2: INTENT & SEARCH ROUTING VERIFICATION")
    print("="*95)
    print(f"{'Query':<48} {'Intent':<16} {'Search':<8} {'LiveSearch':<12} {'Status'}")
    print("-"*95)

    all_pass = True

    # ── Section 1: Standalone Tests ───────────────────────────────────────────
    for query, allowed_intents, exp_search in STANDALONE_TESTS:
        _live_search_called.clear()
        bot.clear()

        try:
            result = bot.chat(query)
        except Exception as e:
            print(f"ERROR on {query!r}: {e}")
            all_pass = False
            continue

        got_intent = result.get('intent', '?')
        got_search = result.get('search_required')
        live_called = len(_live_search_called) > 0
        live_label  = "CALLED" if live_called else "NOT CALLED"

        intent_ok = got_intent in allowed_intents
        search_ok = got_search == exp_search
        search_consistency_ok = (live_called == exp_search)

        overall_ok = intent_ok and search_ok and search_consistency_ok
        symbol = PASS_SYMBOL if overall_ok else FAIL_SYMBOL

        q_short = query[:46] + ".." if len(query) > 46 else query
        print(f"{q_short:<48} {got_intent:<16} {str(got_search):<8} {live_label:<12} {symbol}")

        if not intent_ok:
            print(f"  ** INTENT mismatch: expected one of {allowed_intents!r} got {got_intent!r}")
        if not search_ok:
            print(f"  ** SEARCH_REQUIRED mismatch: expected {exp_search} got {got_search}")
        if not search_consistency_ok:
            print(f"  ** LIVE_SEARCH consistency: search_required={exp_search} but live_search={'WAS' if live_called else 'WAS NOT'} called")

        if not overall_ok:
            all_pass = False

    # ── Section 2: Conversational Follow-Up Tests ─────────────────────────────
    print("\n" + "-"*95)
    print("MULTI-TURN CONVERSATIONAL FOLLOW-UP TESTS")
    print("-"*95)

    for conv in CONVERSATION_TESTS:
        print(f"\n[Thread: {conv['name']}]")
        bot.clear()

        for turn_idx, (turn_query, allowed_intents, exp_search, exp_live) in enumerate(conv["turns"], 1):
            _live_search_called.clear()
            try:
                result = bot.chat(turn_query)
            except Exception as e:
                print(f"  Turn {turn_idx} ERROR on {turn_query!r}: {e}")
                all_pass = False
                continue

            got_intent = result.get('intent', '?')
            got_search = result.get('search_required')
            live_called = len(_live_search_called) > 0
            live_label  = "CALLED" if live_called else "NOT CALLED"

            intent_ok = got_intent in allowed_intents
            search_ok = got_search == exp_search
            live_ok   = (live_called == exp_live)

            overall_ok = intent_ok and search_ok and live_ok
            symbol = PASS_SYMBOL if overall_ok else FAIL_SYMBOL

            q_short = turn_query[:44] + ".." if len(turn_query) > 44 else turn_query
            print(f"  Turn {turn_idx}: {q_short:<40} {got_intent:<16} {str(got_search):<8} {live_label:<12} {symbol}")

            if not intent_ok:
                print(f"    ** INTENT mismatch: expected one of {allowed_intents!r} got {got_intent!r}")
            if not search_ok:
                print(f"    ** SEARCH_REQUIRED mismatch: expected {exp_search} got {got_search}")
            if not live_ok:
                print(f"    ** LIVE_SEARCH mismatch: expected {'CALLED' if exp_live else 'NOT CALLED'} got {live_label}")

            if not overall_ok:
                all_pass = False

    print("="*95)
    if all_pass:
        print("\n[ALL PASS] All standalone queries and multi-turn follow-ups passed successfully!")
    else:
        print("\n[SOME FAILURES] See above for details.")
    return all_pass


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
