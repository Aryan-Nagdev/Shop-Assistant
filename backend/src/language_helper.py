"""
language_helper.py – Multilingual & Hindi/Hinglish NLP Helper
Provides language detection, Hindi transliteration mapping, query translation
for SerpAPI search queries, and prompt directives for Groq LLM.
"""
import re

# Devanagari Unicode range
DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')

# Common Hinglish conversational markers
HINGLISH_KEYWORDS = {
    'chahiye', 'batao', 'dikhao', 'kaisa', 'kaise', 'konsa', 'kaunsa', 'kitne',
    'sasta', 'achha', 'accha', 'sabse', 'ke andar', 'me', 'mein', 'wale', 'wali',
    'kare', 'karein', 'kharidna', 'kharide', 'lena', 'leni', 'liye', 'karo',
    'hoga', 'hogi', 'paise', 'rupaye', 'bataiye', 'dikhayein', 'bata do', 'saste'
}

# Common Hindi / Hinglish shopping vocabulary mapping to English search terms
HINDI_TERM_MAP = [
    (r'(?:^|\s)(kya hai|kya hota hai|kya h|kise kehte hain|kise kahte hai|क्या है|क्या होता है|किसे कहते हैं)(?=\s|$|[^\w])', ' what is '),
    (r'(?:^|\s)(kaise kaam karta hai|kaise karta hai|कैसे काम करता है|कैसे काम करती है)(?=\s|$|[^\w])', ' how it works '),
    (r'(?:^|\s)(antar|tulna|kisme antar|kisme farak|अंतर|तुलना|फ़र्क|फर्क)(?=\s|$|[^\w])', ' vs difference '),
    (r'(?:^|\s)(sasta|saste|kam dam|kam keemat|kam daam|कम दाम|सस्ता|सस्ते)(?=\s|$|[^\w])', ' budget affordable '),
    (r'(?:^|\s)(mehanga|mehnge|premium|best quality|महंगा|प्रीमियम)(?=\s|$|[^\w])', ' premium flagship '),
    (r'(?:^|\s)(sabse accha|sabse badhiya|sabse best|सबसे अच्छा|सबसे बढ़िया|सबसे बेहतरीन)(?=\s|$|[^\w])', ' best top rated '),
    (r'(?:^|\s)(joota|joote|jute|जूते|जूता)(?=\s|$|[^\w])', ' shoes '),
    (r'(?:^|\s)(kapde|kapda|कपड़े|कपड़ा)(?=\s|$|[^\w])', ' clothing clothes '),
    (r'(?:^|\s)(ghadi|ghari|ghadiyan|घड़ी|घड़ियां)(?=\s|$|[^\w])', ' smartwatch watch '),
    (r'(?:^|\s)(chashma|chashme|चश्मा)(?=\s|$|[^\w])', ' sunglasses spectacles '),
    (r'(?:^|\s)(khel|khelne ke|खेल)(?=\s|$|[^\w])', ' sports gaming '),
    (r'(?:^|\s)(kitchen ka saman|rasoi ka saman|रसोई)(?=\s|$|[^\w])', ' kitchen appliances '),
    (r'(?:^|\s)(halkaa|halka|हल्का)(?=\s|$|[^\w])', ' lightweight portable '),
    (r'(?:^|\s)(daam|keemat|mulya|मूल्य|दाम|कीमत)(?=\s|$|[^\w])', ' price '),
    (r'(?:^|\s)(tshirt|t shirt|टीशर्ट)(?=\s|$|[^\w])', ' t-shirt '),
    (r'(?:^|\s)(pant|pents|पैंट)(?=\s|$|[^\w])', ' pants trousers '),
    (r'(?:^|\s)(mobile|fon|phone|फोन|मोबाइल)(?=\s|$|[^\w])', ' phone mobile smartphone '),
    (r'(?:^|\s)(earbuds|earphones|headphones|इयरबड्स|हेडफ़ोन)(?=\s|$|[^\w])', ' earbuds earphones headphones '),
]

# Devanagari Hindi Number conversions (e.g., ५००० -> 5000)
DEVA_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')


def detect_language(text: str, default_lang: str = 'en') -> str:
    """
    Detect whether the input query is Hindi (Devanagari), Hinglish, or English.
    Returns: 'hi' (Devanagari Hindi), 'hinglish', or 'en'.
    """
    if not text or not isinstance(text, str):
        return default_lang

    # Check for Devanagari script
    if DEVANAGARI_RE.search(text):
        return 'hi'

    # Check for Hinglish keywords
    tokens = set(re.findall(r'\b[a-zA-Z]+\b', text.lower()))
    hinglish_matches = tokens.intersection(HINGLISH_KEYWORDS)
    if len(hinglish_matches) >= 1:
        return 'hinglish'

    return default_lang if default_lang in ('hi', 'hinglish') else 'en'


def normalize_devanagari_numbers(text: str) -> str:
    """Convert Hindi Devanagari digits to standard Arabic digits (1, 2, 3, etc.)."""
    if not text:
        return ""
    return text.translate(DEVA_DIGITS)


def clean_hindi_query_for_search(query: str) -> str:
    """
    Normalizes Hindi / Hinglish terms to English e-commerce terms
    suitable for SerpAPI / Google Shopping queries.
    """
    q = normalize_devanagari_numbers(query)

    for pattern, replacement in HINDI_TERM_MAP:
        q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)

    # Remove generic Hindi question wrappers
    q = re.sub(
        r'(?:^|\s)(mujhe|chahiye|dikhao|batao|bata do|dikhaiye|bataiye|lena hai|kharidna hai|'
        r'konsa|kaunsa|kaisa|kaise|kitne ka|ka|ki|ke|me|mein|se|aur|bhi|'
        r'मुझे|चाहिए|दिखाओ|बताओ|बताइए|खरीदना है|लेना है|कौनसा|कैसा|का|की|के|में)(?=\s|$|[^\w])',
        ' ',
        q,
        flags=re.IGNORECASE
    )

    q = re.sub(r'\s+', ' ', q).strip()
    return q


def get_language_prompt_directive(language: str) -> str:
    """
    Returns system prompt instructions for LLM to produce response in the user's desired language.
    """
    if language == 'hi':
        return (
            "IMPORTANT LANGUAGE DIRECTIVE:\n"
            "- The user prefers HINDI (हिन्दी).\n"
            "- Write the 'explanation' and any textual reasoning in natural, respectful Hindi (Devanagari script).\n"
            "- Retain brand names (e.g. boAt, Samsung, Apple, Nike), technical specs (e.g. 5000mAh, 120Hz, ANC, 8GB RAM, i5), "
            "and numerical pricing formatted with the Rupee symbol (₹ e.g. ₹15,999) clearly.\n"
            "- Ensure 'search_queries' remain in ENGLISH for Google Shopping India e-commerce indexing."
        )
    elif language == 'hinglish':
        return (
            "IMPORTANT LANGUAGE DIRECTIVE:\n"
            "- The user prefers HINGLISH (conversational Hindi written in English/Latin script).\n"
            "- Write the 'explanation' in smooth, friendly Hinglish (e.g., 'Agar aapka budget ₹20,000 hai, toh yeh phones best value offer karte hain...').\n"
            "- Retain brand names, technical specs, and ₹ pricing clearly.\n"
            "- Ensure 'search_queries' remain in ENGLISH for Google Shopping India e-commerce indexing."
        )
    else:
        return (
            "LANGUAGE DIRECTIVE:\n"
            "- Respond in clear, helpful English with Indian e-commerce context (₹ INR pricing, Indian retailers)."
        )
