"""
02_prepare_data.py
────────────────────────────────────────────────────────────────
Add intent label, feature tags, and search_text to every clean record.

Fixes:
  1. No longer duplicates intent/feature logic — imports from nlu_engine.py
  2. BRANDS_FLAT deduplication — no double entries
  3. Error handling for malformed clean_data.json
  4. Shows per-intent counts at the end for verification
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tqdm import tqdm
import config

# Import shared NLU logic instead of duplicating it
from nlu_engine import detect_intent, extract_entities


def prepare_record(i: int, rec: dict) -> dict:
    """Tag a single record with intent, features and search_text."""
    q      = rec['question']
    intent = detect_intent(q)
    ents   = extract_entities(q)

    # Flatten entities into a features dict for storage
    features = {
        'colors':    ents.get('colors', []),
        'brands':    ents.get('brands', []),
        'materials': ents.get('materials', []),
        'sizes':     ents.get('sizes', []),
        'max_price': ents.get('max_price'),
        'gaming':    ents.get('gaming', False),
        'wireless':  ents.get('wireless', False),
        'gender':    ents.get('gender'),
    }

    return {
        'id':           i,
        'question':     q,
        'answer':       rec['answer'],
        'category':     rec.get('category', ''),
        'asin':         rec.get('asin', ''),
        'questionType': rec.get('questionType', 'open-ended'),
        'intent':       intent,
        'features':     features,
        # search_text used for FAISS embedding — combines question + answer
        'search_text':  q + ' ' + rec['answer'],
    }


if __name__ == '__main__':
    print("=" * 65)
    print("STEP 2 – Tag Intent & Features")
    print("=" * 65)

    clean_path = os.path.join(config.DATA_DIR, 'clean_data.json')
    if not os.path.exists(clean_path):
        print(f"ERROR: {clean_path} not found.")
        print("Run 01_clean_data.py first.")
        sys.exit(1)

    try:
        with open(clean_path, encoding='utf-8') as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: clean_data.json is malformed: {e}")
        sys.exit(1)

    if not records:
        print("ERROR: clean_data.json is empty. Re-run Step 1.")
        sys.exit(1)

    print(f"Loaded {len(records):,} clean records\n")

    prepared = []
    errors   = 0
    for i, rec in enumerate(tqdm(records, desc="Tagging")):
        try:
            prepared.append(prepare_record(i, rec))
        except Exception as e:
            errors += 1
            if errors <= 5:   # only show first 5 errors
                print(f"\n  ⚠️  Record {i} failed: {e}")

    if errors:
        print(f"\n  ⚠️  {errors} records skipped due to errors.")

    # Save
    with open(config.PROCESSED_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(prepared, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(prepared):,} records → {config.PROCESSED_DATA_PATH}")

    # Intent distribution report
    from collections import Counter
    intent_counts = Counter(r['intent'] for r in prepared)
    print("\nIntent distribution:")
    for k, v in intent_counts.most_common():
        bar = '█' * (v // max(1, max(intent_counts.values()) // 30))
        print(f"  {k:<25} {v:>6}  {bar}")

    # Category distribution
    cat_counts = Counter(r['category'] for r in prepared)
    print("\nCategory distribution:")
    for k, v in sorted(cat_counts.items()):
        print(f"  {k:<42} {v:>5}")

    print("\n✅  Step 2 complete!")
