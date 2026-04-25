"""
app.py – Flask REST API + Web UI
"""
import os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import config
from chatbot import ShopBot

app = Flask(__name__, template_folder='templates', static_folder='static')
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
    data = request.get_json(force=True) or {}
    msg  = (data.get('message') or '').strip()
    sid  = data.get('session_id') or session.get('sid', 'default')
    if not msg:
        return jsonify({'error': 'Empty message'}), 400
    result = get_bot(sid).chat(msg)
    return jsonify({
        'answer':   result['answer'],
        'intent':   result['intent'],
        'entities': result['entities'],
        'products': result['products'],
    })

@app.route('/api/clear', methods=['POST'])
def clear():
    data = request.get_json(force=True) or {}
    sid  = data.get('session_id') or session.get('sid', 'default')
    get_bot(sid).clear()
    return jsonify({'status': 'ok'})

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'region': 'India 🇮🇳', 'currency': '₹ INR'})

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

if __name__ == '__main__':
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
