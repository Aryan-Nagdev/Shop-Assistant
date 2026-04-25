'use strict';

// ── Session ID ─────────────────────────────────────────────────────────────
const SID = 'sb_' + Math.random().toString(36).slice(2, 10);

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const msgBox    = $('messages');
const form      = $('form');
const inp       = $('inp');
const sendBtn   = $('sendBtn');
const clearBtn  = $('clearBtn');
const chipsEl   = $('chips');
const intentBar = $('intentBar');
const intentTxt = $('intentText');
const intentIcn = $('intentIcon');
const menuToggle = $('menuToggle');
const sidebar   = $('sidebar');

// ── Intent labels & icons ──────────────────────────────────────────────────
const INTENT_META = {
  comparison:       { icon: '⚖️', label: 'Comparing products side-by-side' },
  price_filter:     { icon: '₹',  label: 'Budget filter applied' },
  best_in_category: { icon: '🏆', label: 'Finding top picks' },
  single_best:      { icon: '🥇', label: 'Finding the single best option' },
  recommendation:   { icon: '🎯', label: 'Personalised recommendation' },
  outfit:           { icon: '👗', label: 'Outfit suggestion' },
  pairing:          { icon: '✨', label: 'Fashion pairing' },
  tech_spec:        { icon: '⚙️', label: 'Tech specs matched' },
  how_to:           { icon: '📖', label: 'How-to / Info query' },
  info_only:        { icon: '💬', label: 'Answering your question' },
  product_search:   { icon: '🔍', label: 'Searching products' },
  price_query:      { icon: '💰', label: 'Price lookup' },
};

// ── Mobile sidebar toggle ──────────────────────────────────────────────────
let overlay = null;
function createOverlay() {
  if (overlay) return;
  overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.appendChild(overlay);
  overlay.addEventListener('click', closeSidebar);
}
function openSidebar() {
  createOverlay();
  sidebar.classList.add('open');
  overlay.classList.add('active');
}
function closeSidebar() {
  sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('active');
}
menuToggle.addEventListener('click', () => {
  sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
});

// ── Load suggestion chips ──────────────────────────────────────────────────
async function loadChips() {
  try {
    const res  = await fetch('/api/suggestions');
    const list = await res.json();
    chipsEl.innerHTML = list.map(s =>
      `<button class="chip" type="button" onclick="fillInp(${JSON.stringify(s.text)})">${s.icon} ${s.text}</button>`
    ).join('');
  } catch (e) {
    console.warn('Could not load chips:', e);
  }
}
function fillInp(text) {
  inp.value = text;
  inp.focus();
  closeSidebar();
}

// ── Form submit ────────────────────────────────────────────────────────────
form.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = inp.value.trim();
  if (!msg || sendBtn.disabled) return;
  inp.value = '';
  sendBtn.disabled = true;
  hideIntentBar();

  addUserMsg(msg);
  const typingEl = addTyping();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, session_id: SID }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    typingEl.remove();
    addBotMsg(data);
    showIntent(data.intent);
  } catch (err) {
    typingEl.remove();
    addBotMsg({
      answer: `⚠️ **Could not reach the server.** Make sure ShopBot is running on \`localhost:5000\` and try again.`,
      products: [],
      intent: '',
    });
  } finally {
    sendBtn.disabled = false;
    inp.focus();
    scrollToBottom();
  }
});

// ── Clear chat ─────────────────────────────────────────────────────────────
clearBtn.addEventListener('click', async () => {
  try {
    await fetch('/api/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: SID }),
    });
  } catch {}
  msgBox.innerHTML = '';
  hideIntentBar();
  addGreeting();
  closeSidebar();
});

// ── Keyboard: Enter to send, Shift+Enter for newline ──────────────────────
inp.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    form.dispatchEvent(new Event('submit'));
  }
});

// ── Greeting ───────────────────────────────────────────────────────────────
function addGreeting() {
  addBotMsg({
    answer: [
      `**Namaste! 🙏 I'm ShopBot India** — your AI shopping assistant.`,
      ``,
      `Here's what I can do for you:`,
      `- ⚖️ **Compare brands** — e.g. *"Realme vs Vivo gaming phone"*`,
      `- 💰 **Filter by budget** — e.g. *"Best phone under ₹15,000"*`,
      `- 🥇 **Best single pick** — e.g. *"Suggest 1 best gaming laptop"*`,
      `- 👗 **Outfit pairing** — e.g. *"Jeans for a blue t-shirt"*`,
      `- 📖 **Product info** — e.g. *"How to choose a DSLR"*`,
      `- 🔍 **Search anything** — with live ₹ prices from Indian stores`,
      ``,
      `Pick a suggestion on the left, or just type your query!`,
    ].join('\n'),
    products: [],
    intent: '',
  });
}

// ── Message renderers ──────────────────────────────────────────────────────
function addUserMsg(text) {
  const el = makeEl('div', 'msg user');
  el.innerHTML = `
    <div class="av usr">👤</div>
    <div class="bubble">${escHtml(text)}</div>
  `;
  msgBox.appendChild(el);
  scrollToBottom();
}

function addBotMsg(data) {
  const el = makeEl('div', 'msg');
  const html = mdToHtml(data.answer || '');
  const products = data.products || [];
  const intent = data.intent || '';

  let cardsHtml = '';
  if (products.length > 0) {
    if (intent === 'single_best') {
      cardsHtml = `<div class="cards-single">${productCard(products[0], true)}</div>`;
    } else {
      cardsHtml = `<div class="cards-grid">${products.map(p => productCard(p, false)).join('')}</div>`;
    }
  }

  el.innerHTML = `
    <div class="av bot">🤖</div>
    <div class="bubble bot">${html}${cardsHtml}</div>
  `;
  msgBox.appendChild(el);
  scrollToBottom();
}

function addTyping() {
  const el = makeEl('div', 'msg');
  el.innerHTML = `
    <div class="av bot">🤖</div>
    <div class="bubble bot">
      <div class="typing"><span></span><span></span><span></span></div>
    </div>
  `;
  msgBox.appendChild(el);
  scrollToBottom();
  return el;
}

// ── Product card ───────────────────────────────────────────────────────────
function productCard(p, large = false) {
  // ── Resolve link ──────────────────────────────────────────────────────
  // Priority: 1) p.link if it's a real URL, 2) p.product_link, 3) Flipkart search fallback
  let href = '';
  const rawLink = (p.link || p.product_link || '').trim();

  if (rawLink && rawLink.startsWith('http')) {
    href = rawLink;
  } else if (p.title) {
    // Fallback: Flipkart search (reliable Indian store)
    href = `https://www.flipkart.com/search?q=${encodeURIComponent(p.title)}`;
  } else {
    href = 'https://www.flipkart.com';
  }

  // ── Image ──────────────────────────────────────────────────────────────
  const imgSrc = p.thumbnail || p.image || '';
  const imgHtml = imgSrc
    ? `<img class="card-img" src="${escAttr(imgSrc)}" alt="${escAttr(p.title || '')}"
           loading="lazy"
           onerror="this.style.display='none';this.nextSibling.style.display='flex'"
       /><div class="card-img-ph" style="display:none">🛍️</div>`
    : `<div class="card-img-ph">🛍️</div>`;

  // ── Source badge ───────────────────────────────────────────────────────
  const source = p.source || detectSource(href);
  const sourceBadge = source
    ? `<div class="card-source-badge">${escHtml(source)}</div>`
    : '';

  // ── Rating ─────────────────────────────────────────────────────────────
  const ratingHtml = p.rating
    ? `<div class="card-rating">⭐ ${escHtml(String(p.rating))}${p.reviews ? ` <span style="color:var(--text3)">(${fmtReviews(p.reviews)})</span>` : ''}</div>`
    : '';

  // ── Price ──────────────────────────────────────────────────────────────
  const priceStr = p.price_inr || p.price || 'Check price';
  const priceHtml = `<div class="card-price">${escHtml(priceStr)}</div>`;

  const cls = large ? 'card card-large' : 'card';

  // The entire card is clickable (opens in new tab), plus an explicit "View & Buy" anchor
  return `
<div class="${cls}" onclick="safeOpen('${escAttr(href)}')">
  <div class="card-img-wrap">
    ${imgHtml}
    ${sourceBadge}
  </div>
  <div class="card-body">
    <div class="card-title">${escHtml(p.title || 'Product')}</div>
    ${priceHtml}
    ${ratingHtml}
  </div>
  <a class="card-btn"
     href="${escAttr(href)}"
     target="_blank"
     rel="noopener noreferrer"
     onclick="event.stopPropagation()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
      <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
    View &amp; Buy
  </a>
</div>`;
}

// Safe open for onclick (avoids CSP issues with window.open on some browsers)
window.safeOpen = function(url) {
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
};

// Detect store name from URL for the badge
function detectSource(url) {
  const map = {
    'flipkart.com': 'Flipkart',
    'amazon.in': 'Amazon.in',
    'amazon.com': 'Amazon',
    'myntra.com': 'Myntra',
    'ajio.com': 'Ajio',
    'croma.com': 'Croma',
    'reliance': 'Reliance',
    'tatacliq': 'Tata CLiQ',
    'nykaa': 'Nykaa',
    'meesho': 'Meesho',
  };
  try {
    const host = new URL(url).hostname.toLowerCase();
    for (const [key, name] of Object.entries(map)) {
      if (host.includes(key)) return name;
    }
  } catch {}
  return '';
}

// ── Intent bar ─────────────────────────────────────────────────────────────
function showIntent(intent) {
  if (!intent || intent === 'empty') { hideIntentBar(); return; }
  const meta = INTENT_META[intent];
  if (!meta) { hideIntentBar(); return; }
  intentIcn.textContent = meta.icon;
  intentTxt.textContent = meta.label;
  intentBar.style.display = 'flex';
}
function hideIntentBar() {
  intentBar.style.display = 'none';
}

// ── Utilities ──────────────────────────────────────────────────────────────
function scrollToBottom() {
  requestAnimationFrame(() => {
    msgBox.scrollTop = msgBox.scrollHeight;
  });
}

function makeEl(tag, cls) {
  const el = document.createElement(tag);
  el.className = cls;
  return el;
}

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(s) {
  return escHtml(s).replace(/'/g, '&#39;');
}

function fmtReviews(n) {
  const x = parseInt(n, 10);
  if (isNaN(x)) return String(n);
  if (x >= 1000) return (x / 1000).toFixed(1) + 'k';
  return String(x);
}

// ── Markdown to HTML ───────────────────────────────────────────────────────
// Handles: **bold**, *italic/em*, ## headings, - lists, • lists, [links](url),
//          `code`, ---, and newlines. Safe: applies escaping before markup.
function mdToHtml(raw) {
  // Process line by line for block elements
  const lines = raw.split('\n');
  const out = [];
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Headings
    if (/^## (.+)/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h3>${inlineFormat(line.replace(/^## /, ''))}</h3>`);
      continue;
    }
    if (/^### (.+)/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push(`<h4>${inlineFormat(line.replace(/^### /, ''))}</h4>`);
      continue;
    }

    // HR
    if (/^---+$/.test(line.trim())) {
      if (inList) { out.push('</ul>'); inList = false; }
      out.push('<hr>');
      continue;
    }

    // Lists (- or • or *)
    if (/^[-•*] (.+)/.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${inlineFormat(line.replace(/^[-•*] /, ''))}</li>`);
      continue;
    }

    // End list
    if (inList && line.trim() === '') {
      out.push('</ul>');
      inList = false;
      continue;
    }

    if (inList) {
      // List continued without bullet — treat as new paragraph
      out.push('</ul>');
      inList = false;
    }

    // Empty line → paragraph break (just skip, paragraphs are wrapping)
    if (line.trim() === '') {
      out.push('<br>');
      continue;
    }

    out.push(`<p>${inlineFormat(line)}</p>`);
  }

  if (inList) out.push('</ul>');
  return out.join('');
}

function inlineFormat(text) {
  // Escape HTML first
  text = escHtml(text);
  // Bold (**text**)
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic/em (*text*)
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Code (`code`)
  text = text.replace(/`([^`]+)`/g, '<code style="background:#1a1f35;padding:1px 5px;border-radius:4px;font-size:12.5px;color:#93c5fd">$1</code>');
  // Links [text](url) — url was HTML-escaped, decode it back for href
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    const safeUrl = url.replace(/&amp;/g, '&');
    return `<a href="${safeUrl}" target="_blank" rel="noopener">${label}</a>`;
  });
  // ₹ highlighting
  text = text.replace(/(₹[\d,]+)/g, '<strong>$1</strong>');
  return text;
}

// ── Init ───────────────────────────────────────────────────────────────────
loadChips();
addGreeting();
inp.focus();
