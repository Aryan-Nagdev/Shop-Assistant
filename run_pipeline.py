"""
run_pipeline.py
One-shot script to run all 3 training steps.
After this completes, run: python app.py
"""
import subprocess, sys, os, time

STEPS = [
    ("Step 1 – Clean Data",            "src/01_clean_data.py"),
    ("Step 2 – Tag Intent & Features", "src/02_prepare_data.py"),
    ("Step 3 – Fine-tune SLM + FAISS", "src/03_build_embeddings.py"),
]

def run(label: str, script: str):
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")

    # Check script exists before running
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    if not os.path.exists(script_path):
        print(f"  ⚠️  Script not found: {script_path}")
        print(f"  Skipping {label}.")
        return

    start = time.time()
    r = subprocess.run(
        [sys.executable, script],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    elapsed = time.time() - start

    if r.returncode != 0:
        print(f"\n❌  {label} failed (exit code {r.returncode})")
        print(f"   Check the error above and fix before continuing.")
        sys.exit(r.returncode)

    print(f"  ✅  {label} done in {elapsed:.1f}s")


if __name__ == '__main__':
    print("\n🚀  ShopBot India — Training Pipeline")
    print(f"{'='*65}")
    print(f"  Python: {sys.executable}")
    print(f"  CWD:    {os.path.dirname(os.path.abspath(__file__))}")
    print(f"{'='*65}")

    total_start = time.time()

    for label, script in STEPS:
        run(label, script)

    total = time.time() - total_start

    print(f"\n{'='*65}")
    print(f"  ✅  All steps complete! Total time: {total:.1f}s")
    print(f"  👉  Now run:   python app.py")
    print(f"  🌐  Then open: http://localhost:5000")
    print(f"{'='*65}\n")
