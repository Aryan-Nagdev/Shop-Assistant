"""
01_clean_data.py
────────────────────────────────────────────────────────────────
Reads Amazon QA dataset files and produces a clean balanced dataset.

FILE DISCOVERY (handles both layouts):
  (a) data/qa_Electronics.json          ← plain file
  (b) data/qa_Electronics.json/         ← FOLDER (Amazon's actual layout)
        qa_Electronics.json             ← file inside
        or multiple shard files

LINE FORMAT:  Python dict strings  {'key': 'val', ...}
              Parsed with ast.literal_eval

CLEANING (strict):
  ✗  question  < 10 chars or < 3 words
  ✗  answer    < 20 chars or < 4 words
  ✗  answer is pure yes/no/nah/yep
  ✗  evasive starters (I don't know, not sure …)
  ✗  emotional/spam words
  ✗  exact-duplicate questions (md5)
  ✓  cap: 20 000 rows total, balanced per category

Fixes:
  1. clean_records() was defined but never called — now used properly
  2. cat variable is passed explicitly into clean_records()
  3. Progress shown per file, not just per category
  4. Malformed files are skipped with a warning instead of crashing
"""

import ast, hashlib, json, os, re, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import defaultdict
import config

random.seed(42)


# ── Robust line parser ─────────────────────────────────────────────────────────
def parse_line(line: str):
    line = line.strip()
    if not line:
        return None
    # 1. Python repr dict (Amazon QA actual format)
    try:
        obj = ast.literal_eval(line)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 2. Standard JSON
    try:
        obj = json.loads(line)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return None


# ── File discovery (file OR folder) ───────────────────────────────────────────
def find_json_files(base: str) -> list:
    """Return list of readable file paths under base (file or directory)."""
    if os.path.isfile(base):
        return [base]
    if os.path.isdir(base):
        found = []
        for root, _, files in os.walk(base):
            for f in sorted(files):
                if f.endswith('.json') or f.endswith('.jsonl') or '.' not in f:
                    found.append(os.path.join(root, f))
        return found
    return []


# ── Quality filters ────────────────────────────────────────────────────────────
_BAD_STARTS = [
    "i don't know", "i dont know", "not sure", "no idea", "cannot say",
    "can't say", "i am not sure", "i'm not sure", "sorry i",
    "i have no idea", "i really don't", "unfortunately i",
    "i cannot", "i can't answer", "i have not",
]
_SPAM = [
    "garbage", "junk", "terrible product", "horrible product", "scam",
    "fraud", "worst product", "crap", "useless product", "pathetic",
    "do not buy", "don't buy", "waste of money", "return immediately",
]
_PURE_YES_NO = re.compile(
    r'^\s*(yes|no|yep|nope|nah|yeah|yup|sure|definitely|absolutely'
    r'|correct|right|wrong|false|true|ok|okay)[\s\.\!\?]*$', re.I)


def bad_question(q: str) -> bool:
    q = q.strip()
    if len(q) < config.MIN_QUESTION_LEN:
        return True
    if len(q.split()) < 3:
        return True
    if re.match(r'^[\d\W]+$', q):
        return True
    return False


def bad_answer(a: str) -> bool:
    a = a.strip()
    if len(a) < config.MIN_ANSWER_LEN:
        return True
    if len(a.split()) < 4:
        return True
    if _PURE_YES_NO.match(a):
        return True
    al = a.lower()
    for s in _BAD_STARTS:
        if al.startswith(s):
            return True
    for w in _SPAM:
        if w in al:
            return True
    if re.match(r'^https?://\S+$', a):   # URL-only answer
        return True
    return False


def fp(text: str) -> str:
    """MD5 fingerprint for deduplication."""
    return hashlib.md5(
        re.sub(r'\s+', ' ', text.lower().strip()).encode()
    ).hexdigest()


# ── Per-category loader ────────────────────────────────────────────────────────
def load_category(cat: str, fname: str) -> list:
    """Load all raw records for a category from file or folder."""
    candidates = [
        os.path.join(config.DATA_DIR, fname),
        os.path.join(config.DATA_DIR, fname.replace('.json', '')),
    ]
    files = []
    for c in candidates:
        files = find_json_files(c)
        if files:
            break

    if not files:
        return []

    rows = []
    for fpath in files:
        try:
            with open(fpath, encoding='utf-8', errors='replace') as f:
                content = f.read().strip()
        except Exception as e:
            print(f"    ⚠️  Could not read {fpath}: {e}")
            continue

        if not content:
            continue

        # Whole-file JSON array
        if content.startswith('['):
            try:
                for obj in json.loads(content):
                    if isinstance(obj, dict):
                        obj.setdefault('category', cat)
                        rows.append(obj)
                continue
            except Exception:
                pass   # fall through to line-by-line

        # One-per-line (JSONL or Python repr)
        for line in content.splitlines():
            obj = parse_line(line)
            if obj:
                obj.setdefault('category', cat)
                rows.append(obj)

    return rows


# ── Clean a list of records for a given category ───────────────────────────────
def clean_records(records: list, cat: str, seen_global: set) -> list:
    """
    Filter and deduplicate records for one category.
    seen_global is shared across categories to prevent cross-category duplicates.
    Returns list of clean dicts ready for saving.
    """
    out = []
    for r in records:
        q = str(r.get('question', '')).strip()
        a = str(r.get('answer',   '')).strip()

        if bad_question(q) or bad_answer(a):
            continue

        h = fp(q)
        if h in seen_global:
            continue
        seen_global.add(h)

        out.append({
            'question':     q,
            'answer':       a,
            'asin':         r.get('asin', ''),
            'category':     cat,
            'questionType': r.get('questionType', 'open-ended'),
        })
    return out


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 65)
    print("STEP 1 – Strict Data Cleaning")
    print("=" * 65)

    os.makedirs(config.DATA_DIR, exist_ok=True)

    data_abs = os.path.abspath(config.DATA_DIR)
    print(f"\nLooking in: {data_abs}")
    if os.path.isdir(data_abs):
        for entry in sorted(os.listdir(data_abs)):
            kind = "DIR " if os.path.isdir(os.path.join(data_abs, entry)) else "FILE"
            print(f"  [{kind}] {entry}")
    print()

    MAX_TOTAL = getattr(config, 'MAX_TRAIN_ROWS', 20_000)
    n_cats    = len(config.DATASET_FILES)
    per_cap   = MAX_TOTAL // max(n_cats, 1)

    # Shared dedup set across all categories
    seen_global: set = set()
    per_cat: dict    = {}

    for cat, fname in config.DATASET_FILES.items():
        raw   = load_category(cat, fname)
        clean = clean_records(raw, cat, seen_global)

        # Cap per category for balance
        random.shuffle(clean)
        clean = clean[:per_cap]
        per_cat[cat] = clean

        status = "✓" if clean else "✗  NOT FOUND / EMPTY"
        print(f"  {cat:<42}  raw={len(raw):>6}  clean={len(clean):>6}  {status}")

    # Combine, shuffle, final cap
    all_records: list = []
    for records in per_cat.values():
        all_records.extend(records)

    random.shuffle(all_records)
    final = all_records[:MAX_TOTAL]

    # Save
    out = os.path.join(config.DATA_DIR, 'clean_data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\n{'─' * 65}")
    print(f"Total after balancing + dedup : {len(final):>6}  (cap = {MAX_TOTAL:,})")
    print(f"Saved → {out}")

    if not final:
        print("\n⚠️  0 records saved. Check that your dataset files exist at:")
        for cat, fname in config.DATASET_FILES.items():
            p1 = os.path.join(config.DATA_DIR, fname)
            p2 = os.path.join(config.DATA_DIR, fname.replace('.json', ''))
            exists = os.path.exists(p1) or os.path.exists(p2)
            print(f"    {'✓' if exists else '✗'} {p1}")
    else:
        print("\n✅  Cleaning complete!")
        counts: dict = defaultdict(int)
        for r in final:
            counts[r['category']] += 1
        print("\nRecords per category:")
        for k, v in sorted(counts.items()):
            print(f"  {k:<42} {v:>5}")
