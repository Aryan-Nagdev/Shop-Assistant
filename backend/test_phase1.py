import os
import sys
import json

# Ensure stdout handles utf-8 encoding safely on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.query_understanding import understand

TEST_CASES = [
    # 1. Spelling
    "best laptoop for coding",
    "good eardbuds",
    "best camra phone",
    "wirless earbuds",
    "bluethooth headphones",

    # 2. Brand
    "u s polo shoes",
    "uspolo shirt",
    "samsng phone",
    "real me mobile",
    "fireboltt watch",

    # 3. Colour
    "blu shoes",
    "navy blu t shirt",
    "blk jeans",
    "grey sneakers",

    # 4. Configuration
    "i5 16gb 512 ssd laptop",
    "phone with 5000mah battery",
    "earbuds with anc and 40 hours battery",
    "gaming laptop with rtx graphics",

    # 5. Price
    "under 50k",
    "below ₹30,000",
    "between 20k and 30k",
    "above 15k",

    # 6. Combined
    "i want a blu u s polo shoe under 2k",
    "best laptoop i5 16gb 512 ssd under 50k",
    "good gaming laptoop with graphics under 30k",

    # 7. Invalid/unclear
    "asdfghjkl",
    "something good",
    "what should i buy",

    # 8. Critical Category Test
    "earbuds",
]

print(f"Running {len(TEST_CASES)} Phase 1 test cases...\n")
for idx, q in enumerate(TEST_CASES, 1):
    res = understand(q)
    d = res.to_dict()
    print(f"[{idx:02d}] QUERY: {q}")
    print(f"     Normalized : {d['normalized_query']}")
    print(f"     Category   : {d['category']} (conf: {d['category_confidence']:.2f})")
    print(f"     Brand      : {d['brand']} (conf: {d['brand_confidence']:.2f})")
    print(f"     Color      : {d['color']}")
    print(f"     Specs      : {d['specifications']}")
    print(f"     Price      : {d['price']}")
    print(f"     Use Case   : {d['use_case']}")
    print(f"     Hard Reqs  : {d['hard_requirements']}")
    print(f"     Soft Prefs : {d['soft_preferences']}")
    print(f"     Confidence : {d['overall_confidence']:.2f}")
    print(f"     Clarify    : {d['needs_clarification']}")
    print()
