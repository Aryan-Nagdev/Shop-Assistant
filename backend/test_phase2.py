"""
test_phase2.py  –  Phase 2 Strict Validation & Product Matching Test Suite
─────────────────────────────────────────────────────────────────────────
Verifies:
  1. Audio isolation (earbuds vs headphones vs earphones vs neckbands vs speakers)
  2. Accessory and exclusion filtering (cases, covers, straps, tips, cables)
  3. Brand matching (canonical, aliases, competing brand rejection)
  4. Price constraints (hard budget enforcement, no tolerance)
  5. Configuration & Hardware specs (CPU, RAM, Storage, GPU, ANC)
  6. Missing information handling (3-state MATCH / MISMATCH / UNKNOWN)
  7. Product color matching (actual variant evidence)
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
from src.query_understanding import understand
from src.live_search import (
    NormalizedProduct,
    validate_product,
    normalize_raw_item,
)


def run_test_suite():
    passed_tests = 0
    total_tests = 0

    def assert_validation(
        test_id: str,
        query: str,
        prod_dict: dict,
        expected_valid: bool,
        expected_status: str | None = None,
        expected_reason_substr: str | None = None,
    ):
        nonlocal passed_tests, total_tests
        total_tests += 1

        qu = understand(query)
        norm_p = normalize_raw_item(prod_dict, query)

        v_res = validate_product(
            prod=norm_p,
            target_category=qu.category,
            audio_type=qu.audio_type,
            want_brands=[qu.brand] if qu.brand else [],
            max_price=qu.price.get('max'),
            min_price=qu.price.get('min'),
            tech_specs=qu.specifications,
            want_colors=[qu.color] if qu.color else [],
            hard_requirements=qu.hard_requirements,
            category_confidence=qu.category_confidence,
        )

        ok = (v_res.valid == expected_valid)
        if expected_status:
            ok = ok and (v_res.status == expected_status)
        if expected_reason_substr and not v_res.valid:
            ok = ok and any(expected_reason_substr.lower() in r.lower() for r in v_res.reasons)

        status_tag = "PASS" if ok else "FAIL"
        if ok:
            passed_tests += 1

        print(f"[{status_tag}] {test_id}: {query}")
        print(f"       Product: {norm_p.title} (price: {norm_p.price_inr})")
        print(f"       Result : valid={v_res.valid}, status={v_res.status}, reqs={v_res.requirements}")
        if v_res.reasons:
            print(f"       Reasons: {v_res.reasons}")
        if not ok:
            print(f"       EXPECTED: valid={expected_valid}, status={expected_status}, reason={expected_reason_substr}")
        print()

    print("=" * 80)
    print("PHASE 2 VALIDATION & PRODUCT MATCHING TEST SUITE")
    print("=" * 80 + "\n")

    # ── 1. Audio Isolation Suite ──────────────────────────────────────────────
    print("--- 1. AUDIO ISOLATION TESTS ---")
    
    # 1a. Earbuds
    assert_validation(
        "AUDIO-01",
        "earbuds under 2000",
        {"title": "boAt Airdopes 141 TWS Earbuds - 42H Playtime", "price": 1299, "brand": "boAt"},
        expected_valid=True,
    )
    assert_validation(
        "AUDIO-02",
        "earbuds under 2000",
        {"title": "Sony WH-CH520 Wireless Over-Ear Headphones", "price": 1999, "brand": "Sony"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )
    assert_validation(
        "AUDIO-03",
        "earbuds under 2000",
        {"title": "boAt Rockerz 255 Pro+ Wireless Neckband Earphones", "price": 1499, "brand": "boAt"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )
    assert_validation(
        "AUDIO-04",
        "earbuds under 2000",
        {"title": "JBL C100SI Wired In-Ear Earphones with Mic", "price": 799, "brand": "JBL"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )
    assert_validation(
        "AUDIO-05",
        "earbuds under 2000",
        {"title": "JBL Go 3 Portable Bluetooth Speaker", "price": 1999, "brand": "JBL"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )

    # 1b. Headphones
    assert_validation(
        "AUDIO-06",
        "headphones under 2000",
        {"title": "boAt Rockerz 450 Bluetooth On-Ear Headphones", "price": 1499, "brand": "boAt"},
        expected_valid=True,
    )
    assert_validation(
        "AUDIO-07",
        "headphones under 2000",
        {"title": "Noise Buds VS102 Truly Wireless Earbuds", "price": 1199, "brand": "Noise"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )

    # 1c. Wired Earphones
    assert_validation(
        "AUDIO-08",
        "wired earphones under 1500",
        {"title": "Sony MDR-EX150 In-Ear Wired Earphones", "price": 799, "brand": "Sony"},
        expected_valid=True,
    )
    assert_validation(
        "AUDIO-09",
        "wired earphones under 1500",
        {"title": "boAt Airdopes 141 TWS Earbuds", "price": 1299, "brand": "boAt"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )

    # 1d. Neckband
    assert_validation(
        "AUDIO-10",
        "neckband under 2000",
        {"title": "Realme Buds Wireless 2 Neo Neckband Earphones", "price": 899, "brand": "Realme"},
        expected_valid=True,
    )
    assert_validation(
        "AUDIO-11",
        "neckband under 2000",
        {"title": "Sony WH-CH520 Wireless Over-Ear Headphones", "price": 1990, "brand": "Sony"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Audio type mismatch",
    )

    # ── 2. Accessory Exclusions Suite ─────────────────────────────────────────
    print("--- 2. ACCESSORY & EXCLUSION TESTS ---")
    assert_validation(
        "ACC-01",
        "earbuds",
        {"title": "Silicone Protective Case Cover for boAt Airdopes 141 Earbuds", "price": 299},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="accessory",
    )
    assert_validation(
        "ACC-02",
        "earbuds",
        {"title": "Replacement Memory Foam Ear Tips for TWS Earbuds (3 Pairs)", "price": 199},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="accessory",
    )
    assert_validation(
        "ACC-03",
        "earbuds",
        {"title": "Type-C Fast Charging Cable Cord for Wireless Earbuds", "price": 149},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="accessory",
    )
    assert_validation(
        "ACC-04",
        "laptop",
        {"title": "Waterproof Laptop Sleeve Case Cover with Accessory Pouch", "price": 699},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="accessory",
    )
    assert_validation(
        "ACC-05",
        "phone",
        {"title": "Tempered Glass Screen Protector for iPhone 15", "price": 299},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="accessory",
    )

    # ── 3. Brand Matching Suite ───────────────────────────────────────────────
    print("--- 3. BRAND MATCHING & COMPETING BRAND REJECTION TESTS ---")
    assert_validation(
        "BRAND-01",
        "u s polo shoes",
        {"title": "U.S. Polo Assn. Men Off-White Clarkin Sneakers", "price": 2499, "brand": "U.S. Polo Assn."},
        expected_valid=True,
    )
    assert_validation(
        "BRAND-02",
        "u s polo shoes",
        {"title": "US Polo Assn Men Panal Casual Shoes", "price": 2199, "brand": "US Polo"},
        expected_valid=True,
    )
    assert_validation(
        "BRAND-03",
        "u s polo shoes",
        {"title": "Nike Revolution 6 Running Shoes for Men", "price": 2995, "brand": "Nike"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Competing brand",
    )
    assert_validation(
        "BRAND-04",
        "u s polo shoes",
        {"title": "Puma Flyer Runner Mesh Lightweight Shoes", "price": 2199, "brand": "Puma"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Competing brand",
    )
    assert_validation(
        "BRAND-05",
        "u s polo shoes",
        {"title": "Red Tape Men Classic White Casual Sneakers", "price": 1799, "brand": "Red Tape"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Competing brand",
    )

    # ── 4. Price Constraint Suite ─────────────────────────────────────────────
    print("--- 4. PRICE CONSTRAINT ENFORCEMENT TESTS ---")
    assert_validation(
        "PRICE-01",
        "earbuds under 500",
        {"title": "Noise Buds VS102 Truly Wireless Earbuds", "price": 1199, "brand": "Noise"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="exceeds max budget",
    )
    assert_validation(
        "PRICE-02",
        "i5 laptop under 30000",
        {"title": "ASUS Vivobook 15 Intel Core i5 12th Gen 16GB 512GB SSD Laptop", "price": 48990, "brand": "ASUS"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="exceeds max budget",
    )
    assert_validation(
        "PRICE-03",
        "i5 laptop under 30000",
        {"title": "Lenovo IdeaPad 1 Intel Celeron N4020 8GB RAM 256GB SSD Laptop", "price": 24990, "brand": "Lenovo"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="CPU mismatch",
    )

    # ── 5. Configuration & Specifications Suite ───────────────────────────────
    print("--- 5. CONFIGURATION & SPECIFICATION TESTS ---")
    assert_validation(
        "SPEC-01",
        "i5 16GB 512GB SSD laptop under 50000",
        {"title": "HP 15s Intel Core i5 12th Gen (16GB RAM / 512GB SSD / FHD Laptop)", "price": 49990, "brand": "HP"},
        expected_valid=True,
    )
    assert_validation(
        "SPEC-02",
        "i5 16GB 512GB SSD laptop under 50000",
        {"title": "Lenovo IdeaPad 3 Intel Core i3 12th Gen (16GB RAM / 512GB SSD Laptop)", "price": 38990, "brand": "Lenovo"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="CPU mismatch",
    )
    assert_validation(
        "SPEC-03",
        "i5 16GB 512GB SSD laptop under 50000",
        {"title": "ASUS Vivobook 15 Intel Core i5 12th Gen (8GB RAM / 512GB SSD Laptop)", "price": 44990, "brand": "ASUS"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="RAM mismatch",
    )
    assert_validation(
        "SPEC-04",
        "i5 16GB 512GB SSD laptop under 50000",
        {"title": "Dell Inspiron 3520 Intel Core i5 12th Gen (16GB RAM / 256GB SSD Laptop)", "price": 47990, "brand": "Dell"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Storage mismatch",
    )
    assert_validation(
        "SPEC-05",
        "i5 16GB 512GB SSD laptop under 50000",
        {"title": "Acer Aspire 5 Intel Core i5 13th Gen (16GB RAM / 512GB SSD Laptop)", "price": 54990, "brand": "Acer"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="exceeds max budget",
    )

    # ── 6. Missing Information (UNKNOWN State) Suite ──────────────────────────
    print("--- 6. THREE-STATE (MATCH / MISMATCH / UNKNOWN) TESTS ---")
    assert_validation(
        "UNKNOWN-01",
        "i5 16GB laptop under 50000",
        {"title": "Dell Inspiron 15 Intel Core i5 1235U Laptop (512GB SSD)", "price": 46990, "brand": "Dell"},
        expected_valid=False,
        expected_status="incomplete",
        expected_reason_substr="RAM specification could not be verified",
    )

    # ── 7. Colour Validation Suite ────────────────────────────────────────────
    print("--- 7. COLOUR VALIDATION TESTS ---")
    assert_validation(
        "COLOR-01",
        "blue shoes",
        {"title": "Nike Air Max Blue Running Shoes for Men", "price": 4995, "brand": "Nike"},
        expected_valid=True,
    )
    assert_validation(
        "COLOR-02",
        "blue shoes",
        {"title": "Nike Air Max Black Running Shoes for Men", "price": 4995, "brand": "Nike"},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Color mismatch",
    )
    assert_validation(
        "COLOR-03",
        "blue u s polo shoes under 3000",
        {"title": "U.S. Polo Assn. Men Blue Sneaker Shoes", "price": 2499, "brand": "U.S. Polo Assn."},
        expected_valid=True,
    )
    assert_validation(
        "COLOR-04",
        "blue u s polo shoes under 3000",
        {"title": "U.S. Polo Assn. Men White Sneaker Shoes", "price": 2499, "brand": "U.S. Polo Assn."},
        expected_valid=False,
        expected_status="rejected",
        expected_reason_substr="Color mismatch",
    )

    print("=" * 80)
    print(f"TEST RESULTS: {passed_tests} / {total_tests} PASSED ({passed_tests/total_tests*100:.1f}%)")
    print("=" * 80)


if __name__ == '__main__':
    run_test_suite()
