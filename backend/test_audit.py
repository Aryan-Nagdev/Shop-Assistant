"""
test_audit.py - Runtime verification for Phase 1, Phase 2, Phase 3 audit
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.query_understanding import understand, BRAND_REGISTRY
from src.conversation_manager import ConversationManager, ShoppingContext
from src.nlu_engine import detect_intent, analyse, build_search_queries
from chatbot import ShopBot

def run_tests():
    print("================ RUNNING AUDIT TESTS ================")
    
    # ── Test 1: "compare nike and adidas" ─────────────────────────────────────
    print("\n--- Test 1: 'compare nike and adidas' ---")
    qu1 = understand("compare nike and adidas")
    print(f"QU: intent={qu1.intent}, search_required={qu1.search_required}, brands={qu1.brands}, brand={qu1.brand}")
    assert qu1.intent == "comparison", f"Expected comparison, got {qu1.intent}"
    assert qu1.search_required is False, f"Expected False, got {qu1.search_required}"
    assert set(qu1.brands) == {"Nike", "Adidas"}, f"Expected Nike and Adidas, got {qu1.brands}"
    
    nlu_intent1 = detect_intent("compare nike and adidas")
    print(f"NLU detect_intent: {nlu_intent1}")
    assert nlu_intent1 == "comparison", f"Expected comparison, got {nlu_intent1}"

    # ── Test 2: "which laptop is best hp or dell" ─────────────────────────────
    print("\n--- Test 2: 'which laptop is best hp or dell' ---")
    qu2 = understand("which laptop is best hp or dell")
    print(f"QU: intent={qu2.intent}, search_required={qu2.search_required}, category={qu2.category}, brands={qu2.brands}")
    assert qu2.intent == "comparison", f"Expected comparison, got {qu2.intent}"
    assert qu2.search_required is False, f"Expected False, got {qu2.search_required}"
    assert qu2.category == "laptop", f"Expected laptop, got {qu2.category}"
    assert set(qu2.brands) == {"HP", "Dell"}, f"Expected HP and Dell, got {qu2.brands}"

    nlu_intent2 = detect_intent("which laptop is best hp or dell")
    print(f"NLU detect_intent: {nlu_intent2}")
    assert nlu_intent2 == "comparison", f"Expected comparison, got {nlu_intent2}"

    # ── Test 3: "which laptop is best for college work" ───────────────────────
    print("\n--- Test 3: 'which laptop is best for college work' ---")
    qu3 = understand("which laptop is best for college work")
    print(f"QU: intent={qu3.intent}, search_required={qu3.search_required}, category={qu3.category}, use_case={qu3.use_case}")
    assert qu3.intent in ("recommendation", "product_search"), f"Expected recommendation/product_search, got {qu3.intent}"
    assert qu3.search_required is True, f"Expected search_required=True, got {qu3.search_required}"
    assert qu3.category == "laptop", f"Expected laptop, got {qu3.category}"

    # ── Test 4: "hp laptop i5 processor graphic card under 50k" ───────────────
    print("\n--- Test 4: 'hp laptop i5 processor graphic card under 50k' ---")
    qu4 = understand("hp laptop i5 processor graphic card under 50k")
    print(f"QU: category={qu4.category}, brand={qu4.brand}, price={qu4.price}, specs={qu4.specifications}")
    assert qu4.category == "laptop", f"Expected laptop, got {qu4.category}"
    assert qu4.brand == "HP", f"Expected HP, got {qu4.brand}"
    assert qu4.price.get("max") == 50000, f"Expected 50000, got {qu4.price.get('max')}"
    assert "cpu" in qu4.specifications and qu4.specifications["cpu"] == "i5", f"Expected i5 in specs, got {qu4.specifications}"
    assert "gpu" in qu4.specifications and qu4.specifications["gpu"] == "dedicated", f"Expected dedicated in gpu specs, got {qu4.specifications}"
    assert any("gpu: dedicated" in hr.lower() or "graphic" in hr.lower() for hr in qu4.hard_requirements), f"Expected GPU in hard requirements: {qu4.hard_requirements}"

    # Check search query generated
    ents4 = analyse("hp laptop i5 processor graphic card under 50k")
    ents4['qu'] = qu4
    queries4 = build_search_queries("hp laptop i5 processor graphic card under 50k", "product_search", ents4)
    print(f"Generated search queries: {queries4}")
    sq4 = queries4[0]['query'].lower()
    assert "graphic" not in sq4 or "graphics" in sq4 or "graphic" in sq4, f"Search query: {sq4}"
    # Verify no duplicate words like 'graphic laptop ... graphic card'
    assert not sq4.startswith("graphic laptop"), f"Query started with 'graphic laptop': {sq4}"

    # ── Test 5: "earbuds under 5k" ────────────────────────────────────────────
    print("\n--- Test 5: 'earbuds under 5k' ---")
    qu5 = understand("earbuds under 5k")
    print(f"QU: category={qu5.category}, audio_type={qu5.audio_type}, price={qu5.price}")
    assert qu5.category == "earbuds", f"Expected earbuds, got {qu5.category}"
    assert qu5.price.get("max") == 5000, f"Expected 5000, got {qu5.price.get('max')}"

    # ── Test 6: Multi-turn Follow-ups & None crash check ───────────────────────
    print("\n--- Test 6: Multi-turn Conversation & None checks ---")
    cm = ConversationManager()
    
    # Turn 1
    ctx, qu_t1, eff_q1 = cm.process_turn("hp laptop i5 processor graphic card under 50k")
    print(f"Turn 1: eff_q='{eff_q1}', budget={ctx.max_price}, brand={ctx.brand}")
    assert ctx.max_price == 50000
    assert ctx.brand == "HP"
    
    # Turn 2: "make it 60k" (Budget update - check for None crash and query retention)
    ctx, qu_t2, eff_q2 = cm.process_turn("make it 60k")
    print(f"Turn 2: eff_q='{eff_q2}', budget={ctx.max_price}, brand={ctx.brand}")
    assert ctx.max_price == 60000
    assert qu_t2.price.get("max") == 60000
    assert qu_t2.brand == "HP"
    assert qu_t2.category == "laptop"

    # Turn 3: "without graphics" (Removal)
    ctx, qu_t3, eff_q3 = cm.process_turn("without graphics")
    print(f"Turn 3: eff_q='{eff_q3}', specs={ctx.specifications}")
    assert "gpu" not in ctx.specifications
    assert "gpu" not in qu_t3.specifications

    # Turn 4: "what about dell" (Brand switch)
    ctx, qu_t4, eff_q4 = cm.process_turn("what about dell")
    print(f"Turn 4: eff_q='{eff_q4}', brand={ctx.brand}")
    assert ctx.brand == "Dell"
    assert qu_t4.brand == "Dell"

    # Turn 5: New comparison turn
    ctx, qu_t5, eff_q5 = cm.process_turn("which laptop is best hp or dell")
    print(f"Turn 5: eff_q='{eff_q5}', brands={ctx.brands}, intent={qu_t5.intent}")
    assert qu_t5.intent == "comparison"
    assert set(qu_t5.brands) == {"HP", "Dell"}
    assert eff_q5.lower() == "which laptop is best hp or dell"  # Never replaced with "Dell laptop"!

    print("\n✅ ALL AUDIT TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
