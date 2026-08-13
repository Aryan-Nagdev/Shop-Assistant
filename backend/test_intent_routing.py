"""
test_intent_routing.py
Verifies the 10 required test cases from the intent detection spec.
Reports: original query, detected intent, search_required, live_search called, final response type.
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
    return []   # Return empty -- we just need to know it was invoked

def _tracked_fetch_comparison(*args, **kwargs):
    _live_search_called.append('fetch_comparison')
    return {}   # Return empty

_ls_module.fetch_one        = _tracked_fetch_one
_ls_module.fetch_comparison = _tracked_fetch_comparison

from chatbot import ShopBot

TEST_CASES = [
    # (query, expected_intent, expected_search)
    ("What is ANC?",                                          "information",   False),
    ("Is OLED better than LCD?",                             "information",   False),
    ("Nike or Adidas for running?",                          "comparison",    False),
    ("Just compare Nike and Adidas",                         "comparison",    False),
    ("Compare Nike and Adidas shoes under 5000",             "comparison",    True),
    ("Which earbuds are best?",                              "recommendation", True),
    ("Suggest a laptop for coding",                          "recommendation", True),
    ("Nike shoes under 3000",                                "product_search", True),
    ("i5 laptop 16GB under 50k",                             "product_search", True),
    ("Don't recommend, just compare boAt and JBL earbuds",  "comparison",    False),
]

PASS_SYMBOL = "PASS"
FAIL_SYMBOL = "FAIL"


def run_tests():
    bot = ShopBot()

    print("\n" + "="*90)
    print("INTENT DETECTION TEST RESULTS")
    print("="*90)
    print(f"{'Query':<50} {'Intent':<16} {'Search':<8} {'LiveSearch':<14} {'Status'}")
    print("-"*90)

    all_pass = True
    for query, exp_intent, exp_search in TEST_CASES:
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

        intent_ok = got_intent == exp_intent
        search_ok = got_search == exp_search
        search_consistency_ok = (live_called == exp_search)

        overall_ok = intent_ok and search_ok and search_consistency_ok
        symbol = "[" + PASS_SYMBOL + "]" if overall_ok else "[" + FAIL_SYMBOL + "]"

        q_short = query[:48] + ".." if len(query) > 48 else query
        print(f"{q_short:<50} {got_intent:<16} {str(got_search):<8} {live_label:<14} {symbol}")

        if not intent_ok:
            print(f"  ** INTENT mismatch: expected {exp_intent!r} got {got_intent!r}")
        if not search_ok:
            print(f"  ** SEARCH_REQUIRED mismatch: expected {exp_search} got {got_search}")
        if not search_consistency_ok:
            print(f"  ** LIVE_SEARCH consistency: search_required={exp_search} but live_search={'WAS' if live_called else 'WAS NOT'} called")

        if not overall_ok:
            all_pass = False

    print("="*90)
    if all_pass:
        print("\n[ALL PASS] All 10 test cases passed.")
    else:
        print("\n[SOME FAILURES] See above for details.")
    return all_pass


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
