"""
test_fixes.py – Automated test suite verifying the 3 chatbot fixes:
1. Comparison data handling & empty table prevention
2. Fallback message accuracy (only genuine gibberish/vague queries trigger fallback)
3. Multi-turn context isolation (new product queries discard previous context)
"""
import sys, os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot import ShopBot
from src.query_understanding import understand


def test_fallback_accuracy():
    print("\n" + "=" * 80)
    print("TEST 1: FALLBACK MESSAGE ACCURACY")
    print("=" * 80)

    # Queries that MUST trigger clarification fallback
    gibberish_queries = [
        "asdfghjkl",
        "qwertyuiop",
        "zzzzzz",
        "12384729184",
        "buy",
        "product",
    ]

    # Queries that MUST NOT trigger clarification fallback
    valid_queries = [
        "mechanical keyboard under 3000",
        "wireless mouse for gaming",
        "perfume for men",
        "air fryer for kitchen",
        "black hoodie under 1500",
        "gifts for sister under 2000",
        "what is ANC",
        "explain AMOLED vs OLED",
        "how to choose running shoes",
        "which processor is best for programming",
        "best budget trimmers under 1000",
        "gaming monitor 144hz",
        "water purifier for home",
        "boAt vs Noise earbuds",
    ]

    print("\n--- Verifying Genuine Fallbacks (Should need clarification) ---")
    for q in gibberish_queries:
        qu = understand(q)
        print(f"Query: {q!r:20} -> needs_clarification={qu.needs_clarification} (expected: True)")
        assert qu.needs_clarification, f"Expected {q!r} to need clarification!"

    print("\n--- Verifying Valid Queries (Should NOT need clarification) ---")
    for q in valid_queries:
        qu = understand(q)
        print(f"Query: {q!r:45} -> needs_clarification={qu.needs_clarification} (category={qu.category}, intent={qu.intent})")
        assert not qu.needs_clarification, f"Expected {q!r} NOT to need clarification!"

    print("\n>>> TEST 1 PASSED: Fallback triggers accurately! <<<\n")


def test_context_isolation():
    print("\n" + "=" * 80)
    print("TEST 2: MULTI-TURN CONTEXT ISOLATION & SLOT REFINEMENT")
    print("=" * 80)

    bot = ShopBot()

    # Turn 1: Initial laptop search
    print("\n[Turn 1] User: 'Dell laptop with 16GB RAM and i5 under 60k'")
    res1 = bot.chat("Dell laptop with 16GB RAM and i5 under 60k")
    ctx1 = bot.conversation_mgr.context
    print(f"  Context: category={ctx1.category!r}, brand={ctx1.brand!r}, price={ctx1.max_price}, specs={ctx1.specifications}")
    assert ctx1.category == 'laptop', "Expected category='laptop'"
    assert ctx1.brand == 'Dell', "Expected brand='Dell'"
    assert ctx1.max_price == 60000, "Expected max_price=60000"

    # Turn 2: Follow-up budget modification on the same laptop
    print("\n[Turn 2] User: 'make it 50k' (FOLLOW-UP)")
    res2 = bot.chat("make it 50k")
    ctx2 = bot.conversation_mgr.context
    print(f"  Context: category={ctx2.category!r}, brand={ctx2.brand!r}, price={ctx2.max_price}, specs={ctx2.specifications}")
    assert ctx2.category == 'laptop', "Expected category to remain 'laptop'"
    assert ctx2.brand == 'Dell', "Expected brand to remain 'Dell'"
    assert ctx2.max_price == 50000, "Expected max_price updated to 50000"

    # Turn 3: Completely new product request in the same conversation (boAt earbuds)
    print("\n[Turn 3] User: 'boAt earbuds under 1500' (NEW PRODUCT REQUEST)")
    res3 = bot.chat("boAt earbuds under 1500")
    ctx3 = bot.conversation_mgr.context
    print(f"  Context: category={ctx3.category!r}, brand={ctx3.brand!r}, price={ctx3.max_price}, specs={ctx3.specifications}")
    assert ctx3.category == 'earbuds', f"Expected category='earbuds', got {ctx3.category!r}"
    assert ctx3.brand == 'boAt', f"Expected brand='boAt', got {ctx3.brand!r}"
    assert ctx3.max_price == 1500, f"Expected max_price=1500, got {ctx3.max_price}"
    assert 'ram' not in ctx3.specifications and 'cpu' not in ctx3.specifications, "Old laptop specs must not leak into earbuds!"

    # Turn 4: Another new product request (iPhone 15)
    print("\n[Turn 4] User: 'iPhone 15' (NEW PRODUCT REQUEST)")
    res4 = bot.chat("iPhone 15")
    ctx4 = bot.conversation_mgr.context
    print(f"  Context: category={ctx4.category!r}, brand={ctx4.brand!r}, price={ctx4.max_price}, specs={ctx4.specifications}")
    assert ctx4.category == 'phone', f"Expected category='phone', got {ctx4.category!r}"
    assert ctx4.max_price is None or ctx4.max_price != 1500, "Earbuds 1500 budget must not leak into iPhone 15!"

    # Turn 5: Another new product request (Nike running shoes)
    print("\n[Turn 5] User: 'Nike running shoes under 3000' (NEW PRODUCT REQUEST)")
    res5 = bot.chat("Nike running shoes under 3000")
    ctx5 = bot.conversation_mgr.context
    print(f"  Context: category={ctx5.category!r}, brand={ctx5.brand!r}, price={ctx5.max_price}, specs={ctx5.specifications}")
    assert ctx5.category == 'shoes', f"Expected category='shoes', got {ctx5.category!r}"
    assert ctx5.brand == 'Nike', f"Expected brand='Nike', got {ctx5.brand!r}"
    assert ctx5.max_price == 3000, f"Expected max_price=3000, got {ctx5.max_price}"

    # Turn 6: Relative brand switch (FOLLOW-UP)
    print("\n[Turn 6] User: 'show me adidas instead' (FOLLOW-UP)")
    res6 = bot.chat("show me adidas instead")
    ctx6 = bot.conversation_mgr.context
    print(f"  Context: category={ctx6.category!r}, brand={ctx6.brand!r}, price={ctx6.max_price}, specs={ctx6.specifications}")
    assert ctx6.category == 'shoes', "Expected category='shoes'"
    assert ctx6.brand == 'Adidas', f"Expected brand='Adidas', got {ctx6.brand!r}"
    assert ctx6.max_price == 3000, "Expected max_price=3000 preserved on relative switch"

    print("\n>>> TEST 2 PASSED: Context isolation & multi-turn refinement works flawlessly! <<<\n")


def test_comparison_handling():
    print("\n" + "=" * 80)
    print("TEST 3: COMPARISON INTENT HANDLING")
    print("=" * 80)

    bot = ShopBot()

    # Text-only comparison (search_required = False)
    print("\n[Comparison 1] User: 'what is the difference between OLED and AMOLED?'")
    res1 = bot.chat("what is the difference between OLED and AMOLED?")
    print(f"  Intent: {res1['intent']}")
    print(f"  Search Required: {res1['search_required']}")
    print(f"  Products returned: {len(res1['products'])}")
    print(f"  Answer snippet: {res1['answer'][:120]}...")
    assert res1['products'] == [], "Text-only comparison should return empty products array"

    print("\n>>> TEST 3 PASSED: Comparison handling works as expected! <<<\n")


if __name__ == '__main__':
    test_fallback_accuracy()
    test_context_isolation()
    test_comparison_handling()
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
