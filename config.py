"""
config.py  –  ShopBot India
All paths are ABSOLUTE (derived from this file's location).
API keys are loaded from .env — never hardcoded.
"""
import os
from dotenv import load_dotenv
load_dotenv()

# ── Project root ───────────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── API Keys (from .env only — never hardcode) ────────────────────────────────
SERPAPI_KEY     = os.getenv("SERPAPI_KEY", "")
SCRAPINGDOG_KEY = os.getenv("SCRAPINGDOG_KEY", "")

if not SERPAPI_KEY:
    print("⚠️  WARNING: SERPAPI_KEY not set in .env — live search will not work.")
if not SCRAPINGDOG_KEY:
    print("⚠️  WARNING: SCRAPINGDOG_KEY not set in .env — fallback search disabled.")

# ── SLM Model ─────────────────────────────────────────────────────────────────
SLM_MODEL_NAME      = "sentence-transformers/all-MiniLM-L6-v2"
FINETUNED_MODEL_DIR = os.path.join(ROOT_DIR, "models", "finetuned_minilm")

# ── Paths (all absolute) ──────────────────────────────────────────────────────
DATA_DIR            = os.path.join(ROOT_DIR, "data")
FAISS_INDEX_PATH    = os.path.join(DATA_DIR, "faiss_index.bin")
PROCESSED_DATA_PATH = os.path.join(DATA_DIR, "processed_data.json")
EMBEDDINGS_PATH     = os.path.join(DATA_DIR, "embeddings.npy")

# ── Dataset files ──────────────────────────────────────────────────────────────
DATASET_FILES = {
    "Electronics":                 "qa_Electronics.json",
    "Clothing_Shoes_and_Jewelry":  "qa_Clothing_Shoes_and_Jewelry.json",
    "Home_and_Kitchen":            "qa_Home_and_Kitchen.json",
    "Cell_Phones_and_Accessories": "qa_Cell_Phones_and_Accessories.json",
    "Sports_and_Outdoors":         "qa_Sports_and_Outdoors.json",
    "Health_and_Personal_Care":    "qa_Health_and_Personal_Care.json",
    "Video_Games":                 "qa_Video_Games.json",
}

# ── Training cap ───────────────────────────────────────────────────────────────
MAX_TRAIN_ROWS = 20_000

# ── Data quality thresholds ───────────────────────────────────────────────────
MIN_QUESTION_LEN = 10
MIN_ANSWER_LEN   = 20

# ── India / Search settings ───────────────────────────────────────────────────
COUNTRY         = "in"
LANGUAGE        = "en"
CURRENCY_SYMBOL = "₹"
USD_TO_INR      = 83.5   # approximate — update periodically

INDIAN_DOMAINS = [
    "flipkart.com", "amazon.in", "myntra.com", "ajio.com",
    "meesho.com", "snapdeal.com", "tatacliq.com", "nykaa.com",
    "reliancedigital.in", "croma.com", "vijaysales.com",
]

INDIAN_BRANDS = {
    "Clothing_Shoes_and_Jewelry": [
        "Manyavar", "FabIndia", "W", "Biba", "Global Desi", "Louis Philippe",
        "Van Heusen", "Peter England", "Allen Solly", "Arrow", "Libas",
        "Jaipur Kurti", "Roadster", "HRX", "HERE&NOW", "Being Human",
    ],
    "Electronics": [
        "boAt", "Noise", "Fire-Boltt", "Itel", "Lava", "Micromax",
        "iBall", "Intex", "Karbonn", "Havells", "Voltas", "Bajaj Electricals",
    ],
    "Cell_Phones_and_Accessories": [
        "boAt", "Noise", "Realme", "OnePlus", "Poco", "iQOO",
        "Redmi", "Xiaomi", "Motorola", "Lava", "itel",
    ],
    "Sports_and_Outdoors": [
        "Cosco", "Nivia", "SG", "Kookaburra", "Decathlon",
        "Vector X", "DSC", "SS Cricket", "BAS", "Yonex India",
    ],
    "Health_and_Personal_Care": [
        "Patanjali", "Himalaya", "Dabur", "Mamaearth", "Plum",
        "Wow", "mCaffeine", "Nykaa", "Lotus", "Biotique", "Forest Essentials",
    ],
    "Home_and_Kitchen": [
        "Prestige", "Hawkins", "Pigeon", "Butterfly", "Bajaj",
        "V-Guard", "Crompton", "Usha", "Lifelong", "Borosil", "Milton",
    ],
    "Video_Games": [
        "Redgear", "Cosmic Byte", "Ant Esports", "Zebronics", "Amkette",
    ],
}

# ── Retrieval ──────────────────────────────────────────────────────────────────
TOP_K                = 5
SIMILARITY_THRESHOLD = 0.25

# ── Flask ──────────────────────────────────────────────────────────────────────
HOST  = "0.0.0.0"
PORT  = 5000
DEBUG = True   # set False in production
