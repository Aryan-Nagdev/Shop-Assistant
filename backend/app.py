"""
app.py – Flask REST API + Web UI
"""
import os, sys, uuid
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import config
from chatbot import ShopBot

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sibling_frontend_dist = os.path.join(parent_dir, 'frontend', 'dist')
local_frontend_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'dist')

frontend_dist = sibling_frontend_dist if os.path.exists(sibling_frontend_dist) else local_frontend_dist

if not os.path.exists(frontend_dist):
    app = Flask(__name__, template_folder='templates', static_folder='static')
else:
    app = Flask(__name__, template_folder=frontend_dist, static_folder=frontend_dist, static_url_path='')
app.secret_key = os.urandom(24)
CORS(app)


_bots: dict[str, ShopBot] = {}

def get_bot(sid: str) -> ShopBot:
    if sid not in _bots:
        _bots[sid] = ShopBot()
    return _bots[sid]

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'sid' not in session:
        session['sid'] = str(uuid.uuid4())
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json(force=True) or {}
        msg  = (data.get('message') or '').strip()
        sid  = data.get('session_id') or session.get('sid', 'default')
        lang = data.get('language', 'auto')
        if not msg:
            return jsonify({'error': 'Empty message'}), 400
        result = get_bot(sid).chat(msg, language=lang)
        return jsonify({
            'answer':           result['answer'],
            'intent':           result['intent'],
            'entities':         result['entities'],
            'products':         result['products'],
            'structured_query': result.get('structured_query', {}),
            'language':         result.get('language', lang),
        })
    except Exception as e:
        import traceback
        print("LIVE SEARCH ERROR:", repr(e))
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'answer': "I encountered an issue processing your query. Please try again.",
            'intent': 'error',
            'entities': {},
            'products': [],
            'language': 'en',
        }), 500

@app.route('/api/clear', methods=['POST'])
def clear():
    data = request.get_json(force=True) or {}
    sid  = data.get('session_id') or session.get('sid', 'default')
    get_bot(sid).clear()
    return jsonify({'status': 'ok'})

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'region': 'India 🇮🇳', 'currency': '₹ INR'})

@app.route('/api/debug_search')
def debug_search():
    import os, requests
    import config
    
    serp_key = os.getenv("SERPAPI_KEY", "")
    scrapingdog_key = os.getenv("SCRAPINGDOG_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")
    
    def safe_mask(k):
        if not k: return "MISSING/EMPTY"
        cleaned = k.strip().strip("'\"")
        if len(cleaned) <= 8: return f"TOO_SHORT ({len(cleaned)} chars)"
        return f"{cleaned[:4]}...{cleaned[-4:]} (len: {len(cleaned)})"

    report = {
        'keys': {
            'SERPAPI_KEY': safe_mask(serp_key),
            'SCRAPINGDOG_KEY': safe_mask(scrapingdog_key),
            'GROQ_API_KEY': safe_mask(groq_key)
        },
        'config_keys': {
            'config.SERPAPI_KEY': safe_mask(config.SERPAPI_KEY),
            'config.SCRAPINGDOG_KEY': safe_mask(config.SCRAPINGDOG_KEY)
        },
        'search_test': {}
    }
    
    # Test SerpAPI directly
    if not config.SERPAPI_KEY:
        report['search_test']['serpapi'] = 'Skipped: key missing'
    else:
        try:
            params = {
                'engine':   'google_shopping',
                'q':        'best boat earbuds India',
                'api_key':  config.SERPAPI_KEY,
                'num':      5,
                'gl':       'in',
                'hl':       'en',
                'location': 'India',
            }
            r = requests.get("https://serpapi.com/search.json", params=params, timeout=10)
            res_json = r.json()
            if 'error' in res_json:
                report['search_test']['serpapi'] = f"API Error: {res_json['error']}"
            else:
                items = res_json.get('shopping_results', [])
                report['search_test']['serpapi'] = f"Success! Found {len(items)} items."
        except Exception as e:
            report['search_test']['serpapi'] = f"Exception: {str(e)}"
            
    # Test ScrapingDog directly
    if not config.SCRAPINGDOG_KEY:
        report['search_test']['scrapingdog'] = 'Skipped: key missing'
    else:
        try:
            params = {
                'api_key': config.SCRAPINGDOG_KEY,
                'query':   'best boat earbuds India',
                'results': 5,
                'country': 'IN',
            }
            r = requests.get("https://api.scrapingdog.com/google_shopping", params=params, timeout=10)
            res_json = r.json()
            if 'error' in res_json:
                report['search_test']['scrapingdog'] = f"API Error: {res_json['error']}"
            else:
                items = res_json.get('shopping_results', [])
                report['search_test']['scrapingdog'] = f"Success! Found {len(items)} items."
        except Exception as e:
            report['search_test']['scrapingdog'] = f"Exception: {str(e)}"
            
    return jsonify(report)


@app.route('/api/suggestions')
def suggestions():
    return jsonify([
        {"text": "Dell vs HP laptop for college",          "icon": "💻"},
        {"text": "Best gaming laptop under ₹70000",        "icon": "🎮"},
        {"text": "White printed men's t-shirt under ₹500", "icon": "👕"},
        {"text": "Suggest outfit for office women",        "icon": "👗"},
        {"text": "boAt earbuds under ₹2000",               "icon": "🎧"},
        {"text": "Best phone under ₹15000 India",          "icon": "📱"},
        {"text": "Nike vs Adidas running shoes",           "icon": "👟"},
        {"text": "Best DSLR camera for beginners",         "icon": "📷"},
        {"text": "Prestige vs Hawkins pressure cooker",    "icon": "🍳"},
        {"text": "Waterproof smartwatch under ₹5000",      "icon": "⌚"},
    ])


@app.route('/api/refine_query', methods=['POST'])
def refine_query():
    """
    Intent-aware query suggestion endpoint.
    Accepts: {"query": "<raw user text>", "language": "en"}
    Returns: {"suggestions": ["...", "...", "...", "..."]}
    """
    try:
        data = request.get_json(force=True) or {}
        raw_query = (data.get('query') or '').strip()
        language  = data.get('language', 'en')

        if not raw_query or len(raw_query) < 3:
            return jsonify({'suggestions': []})

        from src.query_suggest import get_query_suggestions
        suggestions_list = get_query_suggestions(raw_query, language=language)
        return jsonify({'suggestions': suggestions_list})

    except Exception as e:
        import traceback
        print("REFINE QUERY ERROR:", repr(e))
        traceback.print_exc()
        return jsonify({'suggestions': []}), 200  # Always 200 — UI degrades gracefully



if __name__ == '__main__':
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
