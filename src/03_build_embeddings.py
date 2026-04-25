"""
03_build_embeddings.py
Fine-tune MiniLM-L6-v2 on QA pairs (max 20k), then build FAISS index.
The SLM is used for QUERY UNDERSTANDING only — not for showing dataset answers.
"""
import json, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import config

random.seed(42)

def load_prepared() -> list:
    with open(config.PROCESSED_DATA_PATH, encoding='utf-8') as f:
        return json.load(f)

def finetune(records: list, save_dir: str):
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader

    print(f"\n── Fine-tuning {config.SLM_MODEL_NAME} ──")
    model = SentenceTransformer(config.SLM_MODEL_NAME)

    # Build (question, answer) positive pairs — use entire 20k set
    examples = [InputExample(texts=[r['question'], r['answer']]) for r in records]
    random.shuffle(examples)
    # Hard cap at MAX_TRAIN_ROWS (already enforced by step 1, but safety net)
    MAX = getattr(config, 'MAX_TRAIN_ROWS', 20_000)
    examples = examples[:MAX]
    print(f"  Training pairs : {len(examples):,}")

    loader  = DataLoader(examples, shuffle=True, batch_size=32)
    loss_fn = losses.MultipleNegativesRankingLoss(model)

    model.fit(
        train_objectives=[(loader, loss_fn)],
        epochs=2,
        warmup_steps=max(100, int(0.1 * len(loader))),
        show_progress_bar=True,
        output_path=save_dir,
    )
    print(f"  Fine-tuned model saved → {save_dir}")
    return model

def build_index(records: list, model):
    import faiss
    print("\n── Encoding records + building FAISS index ──")
    texts = [r['search_text'] for r in records]
    emb = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        normalize_embeddings=True, convert_to_numpy=True,
    ).astype('float32')

    np.save(config.EMBEDDINGS_PATH, emb)
    print(f"  Embeddings saved → {config.EMBEDDINGS_PATH}")

    dim = emb.shape[1]
    if len(emb) < 10_000:
        idx = faiss.IndexFlatIP(dim)
    else:
        nlist = min(256, len(emb) // 39)
        q2  = faiss.IndexFlatIP(dim)
        idx = faiss.IndexIVFFlat(q2, dim, nlist, faiss.METRIC_INNER_PRODUCT)
        idx.train(emb)
    idx.add(emb)
    faiss.write_index(idx, config.FAISS_INDEX_PATH)
    print(f"  FAISS index ({idx.ntotal} vectors) → {config.FAISS_INDEX_PATH}")

if __name__ == '__main__':
    print("=" * 65)
    print("STEP 3 – Fine-tune SLM + Build FAISS Index")
    print("=" * 65)

    if not os.path.exists(config.PROCESSED_DATA_PATH):
        print("ERROR: processed_data.json not found. Run 02_prepare_data.py first.")
        sys.exit(1)

    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.FINETUNED_MODEL_DIR, exist_ok=True)

    records = load_prepared()
    print(f"Records to use for training: {len(records):,}")

    if not records:
        print("ERROR: 0 records. Cannot train. Fix Step 1 first.")
        sys.exit(1)

    from sentence_transformers import SentenceTransformer

    ft_check = os.path.join(config.FINETUNED_MODEL_DIR, 'config.json')
    if os.path.exists(ft_check):
        print(f"\nFine-tuned model already exists → loading from {config.FINETUNED_MODEL_DIR}")
        model = SentenceTransformer(config.FINETUNED_MODEL_DIR)
    else:
        model = finetune(records, config.FINETUNED_MODEL_DIR)

    emb_exists   = os.path.exists(config.EMBEDDINGS_PATH)
    faiss_exists = os.path.exists(config.FAISS_INDEX_PATH)

    if emb_exists and faiss_exists:
        print("\nEmbeddings + FAISS index already exist — skipping rebuild.")
        print("Delete data/embeddings.npy and data/faiss_index.bin to force rebuild.")
    else:
        build_index(records, model)

    print("\n✅  Step 3 complete!")
    print(f"   Model  : {config.FINETUNED_MODEL_DIR}")
    print(f"   Index  : {config.FAISS_INDEX_PATH}")