import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  MessageSquare, 
  Plus, 
  Search, 
  Trash2, 
  ShoppingBag, 
  Sparkles, 
  Send, 
  Paperclip, 
  Mic, 
  MicOff,
  Share2, 
  Settings, 
  X, 
  ChevronRight, 
  ChevronLeft,
  Trash, 
  RefreshCw, 
  Volume2, 
  VolumeX,
  Image as ImageIcon,
  Check,
  MapPin,
  ExternalLink,
  Heart,
  Eye,
  CheckCircle2,
  XCircle,
  Menu,
  Award,
  Sparkle,
  Shirt,
  Laptop,
  Smartphone,
  Headphones,
  Footprints,
  Package,
  Globe,
  ShoppingCart,
  Layers,
  MessageCircle,
  Info,
  Atom,
  ShieldCheck
} from 'lucide-react';

const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? 'http://127.0.0.1:5000' 
  : (import.meta.env.VITE_API_BASE || '');

// ── Component: ProductImage with verified model handling & elegant placeholder ──
const ProductImage = ({ product, className = "w-full h-full object-cover", aspect = "aspect-square", compact = false, containerClassName = "", children }) => {
  const initialUrl = product?.thumbnail || product?.fallback_thumbnail || product?.serpapi_thumbnail || product?.image || '';
  const [srcUrl, setSrcUrl] = useState(initialUrl);
  const [imgError, setImgError] = useState(!initialUrl);
  const [imgLoaded, setImgLoaded] = useState(false);

  useEffect(() => {
    const nextUrl = product?.thumbnail || product?.fallback_thumbnail || product?.serpapi_thumbnail || product?.image || '';
    setSrcUrl(nextUrl);
    setImgError(!nextUrl);
    setImgLoaded(false);
  }, [product?.thumbnail, product?.fallback_thumbnail, product?.serpapi_thumbnail, product?.image]);

  const handleImgError = () => {
    const cur = srcUrl;
    const fb = product?.fallback_thumbnail;
    const sp = product?.serpapi_thumbnail;
    if (fb && cur !== fb) {
      setSrcUrl(fb);
    } else if (sp && cur !== sp) {
      setSrcUrl(sp);
    } else {
      setImgError(true);
    }
  };

  if (imgError || !srcUrl) {
    if (compact) {
      return (
        <div className={`relative ${aspect} bg-zinc-900 border border-zinc-800 rounded-xl flex items-center justify-center text-zinc-600 flex-shrink-0 select-none ${containerClassName}`}>
          <ShoppingBag size={18} />
          {children}
        </div>
      );
    }
    return (
      <div className={`relative w-full ${aspect} bg-zinc-900/80 border border-zinc-800 rounded-xl flex flex-col items-center justify-center p-3 text-center select-none ${containerClassName}`}>
        <div className="w-12 h-12 rounded-xl bg-zinc-800 border border-zinc-700/50 flex items-center justify-center text-zinc-500 mb-2">
          <ShoppingBag size={22} />
        </div>
        <span className="text-[10px] font-bold text-zinc-400 line-clamp-1 px-1">
          {product?.title ? product.title.split(/[\(\/,-]/)[0].trim() : (product?.brand || 'Product')}
        </span>
        {children}
      </div>
    );
  }

  return (
    <div className={`relative w-full ${aspect} bg-[#121214] rounded-xl overflow-hidden border border-zinc-800 ${containerClassName}`}>
      {!imgLoaded && (
        <div className="absolute inset-0 bg-zinc-800/40 animate-pulse" />
      )}
      <img
        src={srcUrl}
        alt={product?.title || 'Product'}
        referrerPolicy="no-referrer"
        loading="lazy"
        onLoad={() => setImgLoaded(true)}
        onError={handleImgError}
        className={`${className} transition-opacity duration-200 ${imgLoaded ? 'opacity-100' : 'opacity-60'}`}
      />
      {children}
    </div>
  );
};

// ── 3D HARDWARE-ACCELERATED STARFIELD BACKGROUND ──
const Starfield = ({ isSpeedUp }) => {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    let animationId;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);
    
    const handleResize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    // Mouse parallax tracking
    let mouseX = 0;
    let mouseY = 0;
    const handleMouseMove = (e) => {
      mouseX = (e.clientX - width / 2) * 0.05;
      mouseY = (e.clientY - height / 2) * 0.05;
    };
    window.addEventListener('mousemove', handleMouseMove);

    // Initialize 3D Stars
    const numStars = 180;
    const stars = [];
    for (let i = 0; i < numStars; i++) {
      stars.push({
        x: Math.random() * width - width / 2,
        y: Math.random() * height - height / 2,
        z: Math.random() * 1000,
        color: i % 4 === 0 ? '#818CF8' : (i % 7 === 0 ? '#10B981' : '#FAFAFA'),
        size: 0.5 + Math.random() * 2
      });
    }

    const animate = () => {
      ctx.fillStyle = isSpeedUp ? 'rgba(5, 5, 5, 0.08)' : 'rgba(5, 5, 5, 0.25)';
      ctx.fillRect(0, 0, width, height);

      const speed = isSpeedUp ? 22 : 1.8;

      for (let i = 0; i < numStars; i++) {
        const star = stars[i];
        star.z -= speed;

        if (star.z <= 0) {
          star.z = 1000;
          star.x = Math.random() * width - width / 2;
          star.y = Math.random() * height - height / 2;
        }

        const px = (star.x - mouseX) * (550 / star.z) + width / 2;
        const py = (star.y - mouseY) * (550 / star.z) + height / 2;

        if (px >= 0 && px < width && py >= 0 && py < height) {
          const starSize = (1 - star.z / 1000) * 2.8 + 0.3;
          ctx.beginPath();
          ctx.arc(px, py, starSize, 0, Math.PI * 2);
          ctx.fillStyle = star.color;
          
          if (star.z < 350) {
            ctx.shadowBlur = 6;
            ctx.shadowColor = star.color;
          } else {
            ctx.shadowBlur = 0;
          }
          ctx.fill();
        }
      }
      ctx.shadowBlur = 0;
      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationId);
    };
  }, [isSpeedUp]);

  return <canvas ref={canvasRef} className="fixed inset-0 w-full h-full pointer-events-none z-0 bg-[#050505]" />;
};

function App() {
  // --- STATE: Conversations ---
  const [conversations, setConversations] = useState(() => {
    const saved = localStorage.getItem('stellar_conversations');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error(e);
      }
    }
    return [
      {
        id: 'welcome-chat',
        title: 'New Conversation',
        messages: [],
        products: []
      }
    ];
  });
  
  const [activeChatId, setActiveChatId] = useState(() => {
    const saved = localStorage.getItem('stellar_active_chat_id');
    return saved || 'welcome-chat';
  });

  // --- STATE: Language Support (EN, HI, HINGLISH) ---
  const [selectedLanguage, setSelectedLanguage] = useState(() => {
    return localStorage.getItem('stellar_language') || 'en';
  });

  // --- STATE: Global Wishlist (Persistent in LocalStorage) ---
  const [wishlist, setWishlist] = useState(() => {
    const saved = localStorage.getItem('stellar_global_wishlist');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error(e);
      }
    }
    return [];
  });

  const [isWishlistOpen, setIsWishlistOpen] = useState(false);

  // Sync to localStorage
  useEffect(() => {
    localStorage.setItem('stellar_conversations', JSON.stringify(conversations));
  }, [conversations]);

  useEffect(() => {
    localStorage.setItem('stellar_active_chat_id', activeChatId);
  }, [activeChatId]);

  useEffect(() => {
    localStorage.setItem('stellar_language', selectedLanguage);
  }, [selectedLanguage]);

  useEffect(() => {
    localStorage.setItem('stellar_global_wishlist', JSON.stringify(wishlist));
  }, [wishlist]);

  const [sidebarSearch, setSidebarSearch] = useState('');
  const [inputMessage, setInputMessage] = useState('');
  
  // Interface Toggle States
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(false);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [toast, setToast] = useState({ message: '', visible: false });

  // Premium Features States
  const [confetti, setConfetti] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [imagePreview, setImagePreview] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [speakingMessageId, setSpeakingMessageId] = useState(null);
  const [quickViewProduct, setQuickViewProduct] = useState(null);

  // ── Material Intelligence State ──────────────────────────────────────────
  // materialCache: { [productTitle]: { status: 'loading'|'done'|'error', data: [] } }
  const [materialCache, setMaterialCache] = useState({});

  // Intent-aware query suggestions
  const [querySuggestions, setQuerySuggestions] = useState([]);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const suggestDebounceRef = useRef(null);
  
  // Dynamic Loading Step State
  const [loadingStep, setLoadingStep] = useState(0);
  useEffect(() => {
    let interval;
    if (isTyping) {
      setLoadingStep(0);
      interval = setInterval(() => {
        setLoadingStep(prev => (prev + 1) % 5);
      }, 1400);
    }
    return () => clearInterval(interval);
  }, [isTyping]);
  
  // Form controls
  const [selectedModel, setSelectedModel] = useState('Stellar AI (Default)');

  // Multilingual Suggestions
  const suggestionsByLang = {
    en: [
      { text: "Compare iPhone vs Samsung", icon: "📱" },
      { text: "Best boAt earbuds under ₹2000", icon: "🎧" },
      { text: "Dell vs HP laptop for coding", icon: "💻" },
      { text: "Nike vs Adidas running shoes", icon: "👟" },
      { text: "Suggest office wear under ₹1500", icon: "👔" },
    ],
    hi: [
      { text: "20000 के अंदर सबसे अच्छा स्मार्टफोन", icon: "📱" },
      { text: "boAt vs Noise के बेस्ट ईयरबड्स", icon: "🎧" },
      { text: "कॉलेज के लिए बेस्ट लैपटॉप 50000 में", icon: "💻" },
      { text: "रनिंग के लिए सबसे अच्छे जूते", icon: "👟" },
      { text: "किफायती कुर्ती और सूट कलेक्शन", icon: "👗" },
    ],
    hinglish: [
      { text: "Best phone under 15000 India", icon: "📱" },
      { text: "boAt vs JBL wireless earbuds comparison", icon: "🎧" },
      { text: "Gaming laptop under 70k with 16GB RAM", icon: "🎮" },
      { text: "Budget running shoes under 2000", icon: "👟" },
      { text: "Casual party wear outfit ideas", icon: "👕" },
    ]
  };

  const currentSuggestions = suggestionsByLang[selectedLanguage] || suggestionsByLang.en;

  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);
  const carouselRefs = useRef({});
  const speechRecognitionRef = useRef(null);
  const materialCacheRef = useRef({});

  // ── fetchMaterials: progressive background loader ────────────────────────
  const fetchMaterials = useCallback(async (product) => {
    if (!product || !product.title) return;
    const key = product.title;
    // Skip if already cached or loading
    if (materialCacheRef.current[key]) return;
    materialCacheRef.current[key] = { status: 'loading', data: [] };
    setMaterialCache(prev => ({ ...prev, [key]: { status: 'loading', data: [] } }));
    try {
      const res = await fetch(`${API_BASE}/api/materials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_title: product.title,
          category:      product.category || '',
          brand:         product.brand    || '',
          description:   '',
        }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const json = await res.json();
      const data = Array.isArray(json.materials) ? json.materials : [];
      materialCacheRef.current[key] = { status: 'done', data };
      setMaterialCache(prev => ({ ...prev, [key]: { status: 'done', data } }));
    } catch (e) {
      console.warn('[Materials] fetch failed:', e);
      materialCacheRef.current[key] = { status: 'error', data: [] };
      setMaterialCache(prev => ({ ...prev, [key]: { status: 'error', data: [] } }));
    }
  }, []);

  // --- Auto-scroll to end of chat ---
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversations, activeChatId, isTyping]);

  // --- Auto-grow Input field ---
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [inputMessage]);

  // --- Intent-aware Query Suggestions (debounced) ---
  useEffect(() => {
    if (suggestDebounceRef.current) clearTimeout(suggestDebounceRef.current);

    const trimmed = inputMessage.trim();
    if (trimmed.length < 4) {
      setQuerySuggestions([]);
      setIsSuggesting(false);
      return;
    }

    setIsSuggesting(true);
    suggestDebounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/refine_query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: trimmed, language: selectedLanguage }),
        });
        if (res.ok) {
          const data = await res.json();
          const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
          // Filter out suggestions identical to current input
          setQuerySuggestions(suggestions.filter(s => s.toLowerCase().trim() !== trimmed.toLowerCase()));
        }
      } catch (e) {
        // Silently fail — suggestions are a nice-to-have
        console.warn('[Suggest] fetch failed:', e);
      } finally {
        setIsSuggesting(false);
      }
    }, 650);

    return () => clearTimeout(suggestDebounceRef.current);
  }, [inputMessage, selectedLanguage]);

  const activeChat = conversations.find(c => c.id === activeChatId) || conversations[0] || {
    id: 'temp',
    title: 'New Conversation',
    messages: [],
    products: []
  };

  // Toggle Recommendations Sidebar based on product availability
  useEffect(() => {
    if (activeChat.products && activeChat.products.length > 0) {
      setIsRightSidebarOpen(true);
    }
  }, [activeChatId]);

  // --- TOAST NOTIFICATIONS ---
  const showToast = (message) => {
    setToast({ message, visible: true });
    setTimeout(() => {
      setToast({ message: '', visible: false });
    }, 3000);
  };

  // --- CONFETTI ANIMATION ---
  const triggerConfetti = () => {
    const colors = ['#818CF8', '#10B981', '#F59E0B', '#EF4444', '#EC4899'];
    const newConfetti = [];
    for (let i = 0; i < 40; i++) {
      newConfetti.push({
        id: Math.random(),
        color: colors[Math.floor(Math.random() * colors.length)],
        left: Math.random() * 100,
        size: 5 + Math.random() * 8,
        delay: Math.random() * 0.2,
        duration: 1.5 + Math.random() * 1.5
      });
    }
    setConfetti(newConfetti);
    setTimeout(() => setConfetti([]), 3500);
  };

  // --- WISHLIST MANAGEMENT (LOCAL STORAGE) ---
  const isItemWishlisted = (product) => {
    if (!product) return false;
    return wishlist.some(item => 
      (product.link && item.link === product.link) || 
      (product.title && item.title === product.title)
    );
  };

  const toggleWishlist = (e, product) => {
    if (e) e.stopPropagation();
    if (!product || !product.title) return;

    const exists = isItemWishlisted(product);
    if (exists) {
      setWishlist(prev => prev.filter(item => 
        (product.link ? item.link !== product.link : item.title !== product.title)
      ));
      showToast("Removed from Wishlist");
    } else {
      const productToAdd = {
        title: product.title,
        price_inr: product.price_inr || '₹0',
        mrp_inr: product.mrp_inr || '',
        discount: product.discount || '',
        thumbnail: product.thumbnail || product.fallback_thumbnail || product.serpapi_thumbnail || '',
        fallback_thumbnail: product.fallback_thumbnail || '',
        serpapi_thumbnail: product.serpapi_thumbnail || '',
        brand: product.brand || 'Product',
        rating: product.rating || null,
        reviews: product.reviews || 0,
        source: product.source || 'Store',
        link: product.link || '#',
        addedAt: new Date().toLocaleDateString()
      };
      setWishlist(prev => [productToAdd, ...prev]);
      triggerConfetti();
      showToast("Saved to Wishlist ❤️");
    }
  };

  const removeFromWishlist = (product) => {
    setWishlist(prev => prev.filter(item => 
      (product.link ? item.link !== product.link : item.title !== product.title)
    ));
    showToast("Item removed from Wishlist");
  };

  const clearWishlist = () => {
    setWishlist([]);
    showToast("Wishlist cleared");
  };

  // Calculate total wishlist value
  const totalWishlistValue = wishlist.reduce((sum, item) => {
    const rawPrice = (item.price_inr || '').replace(/[^0-9]/g, '');
    const num = parseInt(rawPrice, 10);
    return sum + (isNaN(num) ? 0 : num);
  }, 0);

  // --- REAL VOICE INPUT: WEB SPEECH API (HINDI & ENGLISH) ---
  const startVoiceInput = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      showToast("Voice input is not supported in this browser. Please use Chrome, Edge, or Safari.");
      return;
    }

    try {
      if (speechRecognitionRef.current) {
        speechRecognitionRef.current.abort();
      }

      const recognition = new SpeechRecognition();
      speechRecognitionRef.current = recognition;

      // Select recognition language based on user's preference
      if (selectedLanguage === 'hi') {
        recognition.lang = 'hi-IN'; // Hindi (India)
      } else if (selectedLanguage === 'hinglish') {
        recognition.lang = 'hi-IN'; // Transcribe Indian speech
      } else {
        recognition.lang = 'en-IN'; // Indian English
      }

      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
        setVoiceTranscript('');
      };

      recognition.onresult = (event) => {
        let currentTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          currentTranscript += event.results[i][0].transcript;
        }
        setVoiceTranscript(currentTranscript);
        setInputMessage(currentTranscript);
      };

      recognition.onerror = (event) => {
        console.warn("Speech recognition error:", event.error);
        setIsListening(false);
        if (event.error === 'not-allowed') {
          showToast("Microphone permission denied. Please allow microphone access.");
        } else if (event.error !== 'no-speech') {
          showToast(`Voice error: ${event.error}`);
        }
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } catch (e) {
      console.error("Voice recognition failed to start:", e);
      setIsListening(false);
      showToast("Could not start voice recognition.");
    }
  };

  const stopVoiceInput = () => {
    if (speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
    }
    setIsListening(false);
  };

  // --- TEXT-TO-SPEECH (TTS) AUDIO SYNTHESIS ---
  const toggleSpeakText = (msgId, text) => {
    if (!('speechSynthesis' in window)) {
      showToast("Text-to-speech is not supported in this browser.");
      return;
    }

    if (speakingMessageId === msgId) {
      window.speechSynthesis.cancel();
      setSpeakingMessageId(null);
      return;
    }

    window.speechSynthesis.cancel();
    // Clean text for speech (remove markdown symbols)
    const cleanText = text
      .replace(/[#*_`]/g, '')
      .replace(/https?:\/\/\S+/g, '')
      .trim();

    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Detect language or voice
    if (selectedLanguage === 'hi') {
      utterance.lang = 'hi-IN';
    } else {
      utterance.lang = 'en-IN';
    }

    const voices = window.speechSynthesis.getVoices();
    const targetVoice = voices.find(v => 
      selectedLanguage === 'hi' ? (v.lang.includes('hi') || v.name.includes('Hindi')) : (v.lang.includes('en-IN') || v.lang.includes('en-GB') || v.lang.includes('en-US'))
    );
    if (targetVoice) utterance.voice = targetVoice;

    utterance.onend = () => {
      setSpeakingMessageId(null);
    };
    utterance.onerror = () => {
      setSpeakingMessageId(null);
    };

    setSpeakingMessageId(msgId);
    window.speechSynthesis.speak(utterance);
  };

  // --- NEW CHAT / DELETE CHAT ---
  const handleNewChat = () => {
    const newId = `chat-${Date.now()}`;
    const newChat = {
      id: newId,
      title: selectedLanguage === 'hi' ? 'नई बातचीत' : 'New Conversation',
      messages: [],
      products: []
    };
    setConversations([newChat, ...conversations]);
    setActiveChatId(newId);
    setIsLeftSidebarOpen(false);
  };

  const handleDeleteChat = (e, id) => {
    e.stopPropagation();
    const remaining = conversations.filter(c => c.id !== id);
    if (remaining.length === 0) {
      const resetChat = {
        id: `chat-${Date.now()}`,
        title: selectedLanguage === 'hi' ? 'नई बातचीत' : 'New Conversation',
        messages: [],
        products: []
      };
      setConversations([resetChat]);
      setActiveChatId(resetChat.id);
    } else {
      setConversations(remaining);
      if (activeChatId === id) {
        setActiveChatId(remaining[0].id);
      }
    }
    showToast("Conversation removed.");
  };

  // --- SAMPLE PROMPT CLICK HANDLER ---
  const handleSamplePromptClick = (text) => {
    if (isTyping || !text) return;
    setInputMessage(text);
    handleSendMessage(text);
  };

  // --- SEND MESSAGE PIPELINE ---
  const handleSendMessage = async (customMessage = null) => {
    if (isTyping) return; // Prevent duplicate submissions while in-flight

    let queryText = '';
    if (typeof customMessage === 'string' && customMessage.trim()) {
      queryText = customMessage.trim();
    } else if (typeof inputMessage === 'string' && inputMessage.trim()) {
      queryText = inputMessage.trim();
    }

    if (!queryText && !imagePreview) return;

    // 1. Append User Message
    const userMsg = {
      id: `msg-${Date.now()}-user`,
      role: 'user',
      content: queryText || "Identify this item from photo snapshot",
      image: imagePreview,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setInputMessage('');
    setImagePreview(null);
    setQuerySuggestions([]);
    setIsSuggesting(false);
    setIsTyping(true);

    const currentChatId = activeChat?.id || activeChatId || 'welcome-chat';

    setConversations(prev => {
      const exists = prev.some(c => c.id === currentChatId);
      if (exists) {
        return prev.map(c => {
          if (c.id === currentChatId) {
            const newTitle = (c.title === 'New Conversation' || c.title === 'नई बातचीत')
              ? (queryText.length > 25 ? `${queryText.substring(0, 25)}...` : queryText)
              : c.title;
            return {
              ...c,
              title: newTitle,
              messages: [...c.messages, userMsg]
            };
          }
          return c;
        });
      } else {
        const newChat = {
          id: currentChatId,
          title: queryText.length > 25 ? `${queryText.substring(0, 25)}...` : queryText,
          messages: [userMsg],
          products: []
        };
        return [newChat, ...prev];
      }
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 35000);

    try {
      // 2. Fetch from Flask backend with language param
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          message: queryText,
          session_id: currentChatId,
          language: selectedLanguage
        })
      });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error("API Offline");
      const result = await response.json();

      // 3. Append Assistant Message
      const isComparison = result.intent === 'comparison';
      let rawProducts = Array.isArray(result.products) ? result.products : [];
      // Client-side deduplication safeguard: ensure every displayed card is a distinct product
      const seenProductKeys = new Set();
      rawProducts = rawProducts.filter(p => {
        if (!p || !p.title) return false;
        const cleanTitleKey = (p.title || '')
          .toLowerCase()
          .replace(/\([^)]*\)/g, '')
          .replace(/\b(?:size|uk|us|eu)\s*[:\-]?\s*\d+\b/g, '')
          .replace(/[^a-z0-9]+/g, ' ')
          .trim()
          .split(' ')
          .slice(0, 5)
          .join(' ');
        if (!cleanTitleKey || seenProductKeys.has(cleanTitleKey)) return false;
        seenProductKeys.add(cleanTitleKey);
        return true;
      });
      const hasComparisonProducts = isComparison && rawProducts.length > 0;

      let comparisonData = null;
      if (hasComparisonProducts) {
        // Build candidate features and extract values safely
        const candidateFeatures = [
          {
            key: 'price',
            label: selectedLanguage === 'hi' ? 'कीमत' : 'Price',
            getValue: (p) => p.price_inr || (p.price ? `₹${p.price.toLocaleString('en-IN')}` : null),
            hasCheck: (p) => Boolean(p.price_inr || p.price)
          },
          {
            key: 'brand',
            label: selectedLanguage === 'hi' ? 'ब्रांड' : 'Brand',
            getValue: (p) => p.brand || null,
            hasCheck: (p) => Boolean(p.brand)
          },
          {
            key: 'rating',
            label: selectedLanguage === 'hi' ? 'रेटिंग' : 'Rating',
            getValue: (p) => p.rating ? `${p.rating} ★` : null,
            hasCheck: (p) => Boolean(p.rating && parseFloat(p.rating) > 0)
          },
          {
            key: 'source',
            label: selectedLanguage === 'hi' ? 'स्टोर' : 'Store Link',
            getValue: (p) => p.source || (p.link ? 'Store' : null),
            hasCheck: (p) => Boolean(p.source || p.link)
          }
        ];

        // Filter so that only features with at least some available information are displayed
        const activeFeatures = candidateFeatures.filter(feat =>
          rawProducts.some(p => feat.getValue(p) !== null)
        );

        if (activeFeatures.length > 0) {
          const ratings = rawProducts.map(p => parseFloat(p.rating) || 0);
          const maxRating = Math.max(...ratings);
          const hasWinner = maxRating >= 4.0;

          comparisonData = {
            features: activeFeatures.map(f => f.label),
            products: rawProducts.map(p => {
              const pRating = parseFloat(p.rating) || 0;
              return {
                name: (p.title || 'Product').length > 25 ? `${(p.title || 'Product').substring(0, 25)}...` : (p.title || 'Product'),
                values: activeFeatures.map(f => f.getValue(p) || 'N/A'),
                checks: activeFeatures.map(f => f.hasCheck(p)),
                isWinner: hasWinner && pRating === maxRating
              };
            }),
            verdict: selectedLanguage === 'hi' 
              ? 'तुलना पूरी हुई। उपलब्ध उत्पाद विवरण ऊपर तालिका में दिखाए गए हैं।'
              : 'Optimized comparison complete. Available product details shown above.'
          };
        }
      }

      const cleanAnswer = (result.answer || '').replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*\*/g, '');
      const aiMsg = {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: cleanAnswer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        componentType: (isComparison && comparisonData) ? 'comparison' : (rawProducts.length > 0 ? 'grid' : null),
        products: rawProducts,
        comparisonData: comparisonData
      };

      if (result.products && result.products.length > 0) {
        setIsRightSidebarOpen(true);
        // Fire-and-forget material fetching for each product (background)
        result.products.forEach(p => fetchMaterials(p));
      }

      setConversations(prev => {
        return prev.map(c => {
          if (c.id === currentChatId) {
            return {
              ...c,
              messages: [...c.messages, aiMsg],
              products: rawProducts
            };
          }
          return c;
        });
      });
    } catch (err) {
      clearTimeout(timeoutId);
      console.warn("Backend request failed:", err);
      
      let errorAnswer = selectedLanguage === 'hi'
        ? "लाइव सर्च सेवा से कनेक्ट करने में समस्या हो रही है। कृपया सुनिश्चित करें कि बैकएंड सर्वर चल रहा है।"
        : "I'm having trouble connecting to the live search service right now. Please verify that the backend server is running and try again.";
      
      if (err.name === 'AbortError') {
        errorAnswer = selectedLanguage === 'hi'
          ? "लाइव प्रोडक्ट डेटा लाने में समय अधिक लगा। कृपया अपना प्रश्न थोड़ा और स्पष्ट लिखकर प्रयास करें।"
          : "The search request timed out while fetching live product data from e-commerce stores. Please try a more specific search.";
      }

      let aiMsg = {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: errorAnswer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        componentType: null,
        products: [],
        comparisonData: null
      };

      setConversations(prev => {
        return prev.map(c => {
          if (c.id === currentChatId) {
            return {
              ...c,
              messages: [...c.messages, aiMsg],
              products: []
            };
          }
          return c;
        });
      });
    } finally {
      setIsTyping(false);
    }
  };

  // Carousel click scroll handler
  const handleCarouselScroll = (msgIndex, direction) => {
    const container = carouselRefs.current[`carousel-${msgIndex}`];
    if (container) {
      const scrollAmt = direction === 'left' ? -300 : 300;
      container.scrollBy({ left: scrollAmt, behavior: 'smooth' });
    }
  };

  // Copy sharing link to clipboard
  const handleShareSession = () => {
    navigator.clipboard.writeText(window.location.origin + "?chat=" + activeChatId);
    showToast("Share link copied to clipboard!");
  };

  // Filter session logs in left panel
  const filteredConversations = conversations.filter(c => 
    c.title.toLowerCase().includes(sidebarSearch.toLowerCase()) ||
    c.messages.some(m => m.content.toLowerCase().includes(sidebarSearch.toLowerCase()))
  );

  // ── Helper: Extract minimal product context for material/spec AI questions ────
  const getMinimalProductContext = (product) => {
    if (!product) return 'these products';
    const rawCat = (product.category || product.dept || '').toLowerCase().trim();
    const tLower = (product.title || '').toLowerCase();

    // Check specific informative subcategories first
    if (tLower.includes('cargo trouser') || tLower.includes('cargo pant') || tLower.includes('parachute trouser') || tLower.includes('parachute cargo')) {
      return 'cargo trousers';
    }
    if (tLower.includes('gaming laptop')) return 'gaming laptops';
    if (tLower.includes('running shoe') || tLower.includes('running sneaker')) return 'running shoes';
    if (tLower.includes('t-shirt') || tLower.includes('tshirt')) return 't-shirts';
    if (tLower.includes('formal shirt') || tLower.includes('casual shirt')) return 'shirts';
    if (tLower.includes('denim jacket') || tLower.includes('leather jacket')) return 'jackets';
    if (tLower.includes('trouser') || tLower.includes('pants')) return 'trousers';
    if (tLower.includes('laptop')) return 'laptops';
    if (tLower.includes('shoes') || tLower.includes('sneaker')) return 'shoes';

    // If clean department or category is available
    if (rawCat && !['electronics', 'clothing_shoes_and_jewelry', 'home_and_kitchen', 'cell_phones_and_accessories', 'apparel'].includes(rawCat)) {
      return rawCat.endsWith('s') ? rawCat : `${rawCat}s`;
    }

    // Clean title: remove slash-separated spec codes, sizes, colors, and percentages
    const title = (product.title || '').trim();
    let base = title.split(/\s*[\/|]\s*|\s+-\s+|\s*\(/)[0].trim();
    base = base.replace(/\b\d{2,3}(?:cm|mm|inch)?\b/gi, '').trim();
    base = base.replace(/\b(?:black|white|blue|navy|grey|gray|green|red|olive|khaki|beige)\b/gi, '').trim();
    base = base.replace(/\s+/g, ' ').trim();
    return base.toLowerCase() || 'this product';
  };

  // ── MaterialSection — Structured E-Commerce "Material & Build" Section ─────────
  const MaterialSection = ({ product, compact = false, onAskAI }) => {
    const key    = product?.title;
    const entry  = key ? materialCache[key] : null;
    const status = entry?.status;
    const mats   = entry?.data || [];

    if (!key) return null;

    // Clean skeleton shimmer while analyzing
    if (status === 'loading') {
      return (
        <div className="mt-2.5 pt-2.5 border-t border-zinc-800/40">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Atom size={10} className="text-indigo-400 animate-spin" style={{ animationDuration: '2s' }} />
            <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider">Analyzing Material & Build...</span>
          </div>
          <div className="space-y-1.5">
            {[1, 2].map(i => (
              <div key={i} className="h-5 w-full bg-zinc-800/40 rounded animate-pulse" style={{ animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        </div>
      );
    }

    if (!status || status === 'error' || mats.length === 0) return null;

    const displayMats = compact ? mats.slice(0, 3) : mats;

    return (
      <div className="mt-2.5 pt-2.5 border-t border-zinc-800/50">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <ShieldCheck size={11} className="text-indigo-400" />
            <span className="text-[9px] font-bold text-zinc-300 uppercase tracking-wider">Material & Build</span>
          </div>
          <span className="text-[8px] font-semibold text-zinc-500 bg-zinc-800/60 px-1.5 py-0.5 rounded border border-zinc-700/40">Specs</span>
        </div>
        
        {/* Structured Spec Rows */}
        <div className="rounded-lg bg-zinc-900/60 border border-zinc-800/60 divide-y divide-zinc-800/40 overflow-hidden">
          {displayMats.map((m, i) => (
            <div 
              key={i} 
              className="flex items-center justify-between px-2 py-1 text-[10px] hover:bg-zinc-800/40 transition-colors group/row cursor-pointer"
              title={m.description || `Ask AI about ${m.material} (${m.part})`}
              onClick={(e) => {
                if (onAskAI) {
                  e.stopPropagation();
                  onAskAI(m.part, m.material);
                }
              }}
            >
              <span className="text-zinc-400 font-medium truncate max-w-[45%] flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-indigo-400/70 shrink-0"></span>
                {m.part}:
              </span>
              <div className="flex items-center gap-1.5 max-w-[55%] justify-end">
                <span className="font-semibold text-zinc-200 truncate">{m.material}</span>
                {onAskAI && (
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      onAskAI(m.part, m.material);
                    }}
                    title={`Ask AI about ${m.material}`}
                    className="opacity-0 group-hover/row:opacity-100 p-0.5 text-indigo-400 hover:text-indigo-300 transition-opacity"
                  >
                    <MessageCircle size={10} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {compact && mats.length > 3 && (
          <span className="text-[8px] text-zinc-500 mt-1 inline-block font-medium">
            +{mats.length - 3} more build specifications
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-textPrimary select-none relative font-sans">
      
      {/* ── 3D COSMIC STARFIELD BACKGROUND ── */}
      <Starfield isSpeedUp={isTyping} />

      {/* ── CONFETTI SHOWER REFERRAL DELIGHT ── */}
      {confetti.map(p => (
        <div 
          key={p.id}
          className="confetti-piece fixed pointer-events-none z-[10000]"
          style={{
            backgroundColor: p.color,
            left: `${p.left}%`,
            top: '-10px',
            width: `${p.size}px`,
            height: `${p.size}px`,
            borderRadius: '2px',
            animation: `fall ${p.duration}s linear forwards`,
            animationDelay: `${p.delay}s`,
          }}
        />
      ))}

      {/* ── MOBILE SIDEBAR DRAWER OVERLAY ── */}
      {isLeftSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsLeftSidebarOpen(false)}
        />
      )}

      {/* ── LEFT GLASSMORPHIC SIDEBAR ── */}
      <aside className={`
        fixed md:static inset-y-0 left-0 w-[280px] bg-chatSurface/70 backdrop-blur-md border-r border-zinc-800/40 
        flex flex-col h-full z-40 transition-transform duration-300 md:translate-x-0
        ${isLeftSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Top Branding Section */}
        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
              Stellar
              <span className="w-2.5 h-2.5 bg-indigo-500 rounded-full shadow-[0_0_10px_#818CF8]"></span>
            </span>
          </div>
          <button className="md:hidden text-zinc-400 hover:text-white" onClick={() => setIsLeftSidebarOpen(false)}>
            <X size={20} />
          </button>
        </div>

        {/* New Session Button */}
        <div className="px-6 pb-4">
          <button 
            className="w-full h-[50px] bg-indigo-600 hover:bg-indigo-500 text-white rounded-2xl font-semibold flex items-center justify-center gap-2 transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-indigo-600/30 active:translate-y-0 active:scale-[0.98]"
            onClick={handleNewChat}
          >
            <Plus size={20} />
            <span>{selectedLanguage === 'hi' ? 'नई बातचीत' : 'New Conversation'}</span>
          </button>
        </div>

        {/* Filter Chat History */}
        <div className="px-6 pb-4">
          <div className="relative flex items-center">
            <Search size={16} className="absolute left-3.5 text-zinc-500" />
            <input 
              type="text"
              placeholder={selectedLanguage === 'hi' ? 'इतिहास खोजें...' : 'Search chat history...'}
              className="w-full h-10 bg-[#171717]/60 border border-zinc-800/60 rounded-xl pl-10 pr-4 text-xs text-textPrimary placeholder-zinc-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
              value={sidebarSearch}
              onChange={(e) => setSidebarSearch(e.target.value)}
            />
          </div>
        </div>

        {/* Sidebar Nav Items */}
        <div className="flex-1 overflow-y-auto px-4 space-y-6">
          
          {/* Recent sessions */}
          <div>
            <h4 className="text-[10px] font-bold text-zinc-500 tracking-wider uppercase mb-2 px-2">
              {selectedLanguage === 'hi' ? 'हालिया बातचीत' : 'Recent Chats'}
            </h4>
            <div className="space-y-1">
              {filteredConversations.map(chat => {
                const isActive = chat.id === activeChatId;
                return (
                  <div
                    key={chat.id}
                    onClick={() => {
                      setActiveChatId(chat.id);
                      setIsLeftSidebarOpen(false);
                    }}
                    className={`
                      group flex items-center gap-3 p-3 rounded-xl cursor-pointer border border-transparent transition-all
                      ${isActive ? 'bg-indigo-600/20 border-indigo-500/30 text-white' : 'hover:bg-[#171717]/40 hover:border-zinc-800/40 text-zinc-300'}
                    `}
                  >
                    <MessageSquare size={16} className={isActive ? 'text-indigo-400' : 'text-zinc-500'} />
                    <span className="flex-1 text-xs font-medium truncate">{chat.title}</span>
                    {conversations.length > 1 && (
                      <button 
                        onClick={(e) => handleDeleteChat(e, chat.id)}
                        className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-rose-500 p-0.5 rounded transition-all"
                        title="Delete session"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Quick Categories explorer */}
          <div>
            <h4 className="text-[10px] font-bold text-zinc-500 tracking-wider uppercase mb-2 px-2">
              {selectedLanguage === 'hi' ? 'श्रेणियां खोजें' : 'Explore Categories'}
            </h4>
            <div className="grid grid-cols-2 gap-2">
              <div 
                className="flex items-center gap-2 p-2 bg-[#171717]/50 hover:bg-zinc-800/50 border border-zinc-800/40 rounded-xl cursor-pointer text-xs font-semibold transition-all hover:border-indigo-500/40"
                onClick={() => {
                  setIsLeftSidebarOpen(false);
                  handleSamplePromptClick(selectedLanguage === 'hi' ? "गेमिंग और कोडिंग के लिए बेस्ट लैपटॉप" : "Compare high performance laptops");
                }}
              >
                <span>💻</span><span className="truncate">Tech</span>
              </div>
              <div 
                className="flex items-center gap-2 p-2 bg-[#171717]/50 hover:bg-zinc-800/50 border border-zinc-800/40 rounded-xl cursor-pointer text-xs font-semibold transition-all hover:border-indigo-500/40"
                onClick={() => {
                  setIsLeftSidebarOpen(false);
                  handleSamplePromptClick(selectedLanguage === 'hi' ? "रनिंग के लिए बेस्ट जूते" : "Best running sneakers");
                }}
              >
                <span>👟</span><span className="truncate">Shoes</span>
              </div>
              <div 
                className="flex items-center gap-2 p-2 bg-[#171717]/50 hover:bg-zinc-800/50 border border-zinc-800/40 rounded-xl cursor-pointer text-xs font-semibold transition-all hover:border-indigo-500/40"
                onClick={() => {
                  setIsLeftSidebarOpen(false);
                  handleSamplePromptClick(selectedLanguage === 'hi' ? "विंटर जैकेट और हुडी" : "Suggest premium winter jackets");
                }}
              >
                <span>🧥</span><span className="truncate">Fashion</span>
              </div>
              <div 
                className="flex items-center gap-2 p-2 bg-[#171717]/50 hover:bg-zinc-800/50 border border-zinc-800/40 rounded-xl cursor-pointer text-xs font-semibold transition-all hover:border-indigo-500/40"
                onClick={() => {
                  setIsLeftSidebarOpen(false);
                  handleSamplePromptClick(selectedLanguage === 'hi' ? "2000 के अंदर boAt वायरलेस ईयरबड्स" : "Top boat Bluetooth earbuds under 2000");
                }}
              >
                <span>🎧</span><span className="truncate">Audio</span>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar Footer User Profile */}
        <div className="p-4 bg-black/50 border-t border-zinc-800/50">
          <div className="flex items-center gap-3">
            <div className="relative flex-shrink-0">
              <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-indigo-500 to-emerald-400 flex items-center justify-center font-bold text-white text-sm">A</div>
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-400 border-2 border-chatSurface rounded-full"></span>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-bold text-white">Aryan Nagdev</span>
              <span className="text-[10px] text-zinc-500 flex items-center gap-1">
                <MapPin size={9} /> India 🇮🇳 (INR ₹)
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── MAIN CHAT PANEL ── */}
      <main className="flex-1 flex flex-col h-full relative overflow-hidden bg-transparent z-10">
        
        {/* Navigation Top Header */}
        <header className="h-16 border-b border-zinc-800/40 bg-chatSurface/60 backdrop-blur-md flex items-center justify-between px-4 sm:px-6 z-30">
          <div className="flex items-center gap-3 min-w-0">
            <button className="md:hidden text-zinc-400 hover:text-white flex-shrink-0" onClick={() => setIsLeftSidebarOpen(true)}>
              <Menu size={20} />
            </button>
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-bold text-white max-w-[150px] sm:max-w-xs truncate">{activeChat.title}</span>
              <span className="text-[10px] text-indigo-400 font-semibold tracking-wider uppercase flex items-center gap-1">
                Stellar AI • India Live Engine
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Language Switcher Pill */}
            <div className="flex items-center bg-[#171717]/70 border border-zinc-800/80 rounded-xl p-1 gap-1">
              <button 
                onClick={() => {
                  setSelectedLanguage('en');
                  showToast("Switched to English");
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                  selectedLanguage === 'en' 
                    ? 'bg-indigo-600 text-white shadow-sm' 
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                }`}
                title="English"
              >
                EN
              </button>
              <button 
                onClick={() => {
                  setSelectedLanguage('hi');
                  showToast("हिन्दी भाषा सक्षम की गई (Hindi Enabled)");
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                  selectedLanguage === 'hi' 
                    ? 'bg-indigo-600 text-white shadow-sm' 
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                }`}
                title="हिन्दी (Hindi)"
              >
                हिन्दी
              </button>
              <button 
                onClick={() => {
                  setSelectedLanguage('hinglish');
                  showToast("Hinglish Mode Enabled");
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                  selectedLanguage === 'hinglish' 
                    ? 'bg-indigo-600 text-white shadow-sm' 
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                }`}
                title="Hinglish"
              >
                Hinglish
              </button>
            </div>

            {/* Wishlist Header Trigger */}
            <button 
              className="relative p-2 border border-zinc-800/60 bg-[#171717]/40 rounded-xl text-zinc-300 hover:text-rose-400 hover:bg-[#171717]/80 transition-all flex items-center gap-1.5"
              onClick={() => setIsWishlistOpen(true)}
              title="Open Wishlist"
            >
              <Heart size={16} fill={wishlist.length > 0 ? '#EF4444' : 'none'} className={wishlist.length > 0 ? 'text-rose-500' : ''} />
              {wishlist.length > 0 && (
                <span className="text-[11px] font-bold text-rose-400 px-1">
                  {wishlist.length}
                </span>
              )}
            </button>

            {/* Recommendations Toggle */}
            <button 
              className="p-2 border border-zinc-800/60 bg-[#171717]/40 rounded-xl text-zinc-400 hover:text-white hover:bg-[#171717]/80 transition-all flex md:hidden"
              onClick={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
              title="Toggle Live Recommendations"
            >
              <ShoppingBag size={15} />
            </button>

            <button className="p-2 border border-zinc-800/60 bg-[#171717]/40 rounded-xl text-zinc-400 hover:text-white hover:bg-[#171717]/80 transition-all" onClick={handleShareSession} title="Copy Share Link">
              <Share2 size={15} />
            </button>

            <button className="p-2 border border-zinc-800/60 bg-[#171717]/40 rounded-xl text-zinc-400 hover:text-white hover:bg-[#171717]/80 transition-all" onClick={() => setIsSettingsOpen(true)} title="Settings & Model Specification">
              <Settings size={15} />
            </button>
          </div>
        </header>

        {/* Viewport Chat Content Area */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-8 space-y-6">
          <div className="max-w-[860px] mx-auto space-y-8">
            
            {activeChat.messages.length === 0 ? (
              // Blank state
              <div className="py-12 text-center max-w-lg mx-auto space-y-8 relative z-10 animate-fade-in">
                <div className="w-16 h-16 bg-[#171717]/70 border border-zinc-800/80 rounded-2xl flex items-center justify-center text-indigo-500 mx-auto shadow-2xl backdrop-blur-md">
                  <ShoppingBag size={28} />
                </div>
                <div className="space-y-3">
                  <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-zinc-200 to-zinc-500 bg-clip-text text-transparent">
                    {selectedLanguage === 'hi' ? 'कुछ भी खोजें। बेहतर खरीदारी करें।' : 'Search anything. Shop smarter.'}
                  </h1>
                  <p className="text-sm text-textSecondary leading-relaxed">
                    {selectedLanguage === 'hi' 
                      ? 'भारतीय ई-कॉमर्स (Amazon.in, Flipkart) से लाइव कीमतें, स्पेसिफिकेशन्स और तुलना तुरंत प्राप्त करें।'
                      : 'Compare features, prices, specifications, and reviews instantly. Integrated with India\'s largest e-commerce stores.'}
                  </p>
                </div>

                {/* Sample Prompt Pills in Hero */}
                <div className="flex flex-wrap gap-2 justify-center pt-2">
                  {currentSuggestions.map((chip, idx) => (
                    <button 
                      key={idx}
                      disabled={isTyping}
                      className="px-3.5 py-1.5 bg-[#171717]/80 hover:bg-zinc-800/80 border border-zinc-800 hover:border-indigo-500/50 text-xs font-semibold rounded-full text-zinc-300 hover:text-white transition-all hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                      onClick={() => handleSamplePromptClick(chip.text)}
                    >
                      <span className="mr-1.5">{chip.icon}</span>
                      <span>{chip.text}</span>
                    </button>
                  ))}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 text-left">
                  <div 
                    className="p-4 bg-[#0A0A0A]/60 hover:bg-zinc-900/60 border border-zinc-800/60 hover:border-indigo-500/50 rounded-2xl space-y-2 cursor-pointer transition-all hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-md group"
                    onClick={() => handleSamplePromptClick(selectedLanguage === 'hi' ? 'iPhone vs Samsung बेस्ट फोन की तुलना करें' : 'Compare iPhone 15 vs Samsung Galaxy S24')}
                  >
                    <Sparkles size={16} className="text-indigo-400 group-hover:scale-110 transition-transform" />
                    <h3 className="text-xs font-bold text-white group-hover:text-indigo-300 transition-colors">
                      {selectedLanguage === 'hi' ? 'ब्रांड्स की तुलना' : 'Compare Tech & Fashion'}
                    </h3>
                    <p className="text-[10px] text-textSecondary leading-normal">
                      {selectedLanguage === 'hi' ? 'साइड-बाय-साइड तुलना और निष्पक्ष विजेता निर्णय।' : 'Interactive side-by-side sheets pitting specs and prices.'}
                    </p>
                    <div className="text-[10px] text-indigo-400 font-semibold pt-1 flex items-center gap-1">
                      <span>{selectedLanguage === 'hi' ? 'क्लिक करें: iPhone vs Samsung ➔' : 'Try: iPhone vs Samsung ➔'}</span>
                    </div>
                  </div>

                  <div 
                    className="p-4 bg-[#0A0A0A]/60 hover:bg-zinc-900/60 border border-zinc-800/60 hover:border-emerald-500/50 rounded-2xl space-y-2 cursor-pointer transition-all hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-md group"
                    onClick={() => handleSamplePromptClick(selectedLanguage === 'hi' ? '60000 के अंदर कोडिंग के लिए बेस्ट लैपटॉप' : 'Best laptop for coding under 60000')}
                  >
                    <CheckCircle2 size={16} className="text-emerald-400 group-hover:scale-110 transition-transform" />
                    <h3 className="text-xs font-bold text-white group-hover:text-emerald-300 transition-colors">
                      {selectedLanguage === 'hi' ? 'सटीक ₹ बजट' : 'Curated INR Deals'}
                    </h3>
                    <p className="text-[10px] text-textSecondary leading-normal">
                      {selectedLanguage === 'hi' ? '₹ कीमतों और छूट के साथ सही सुझाव।' : 'Optimized Indian models with accurate pricing filters.'}
                    </p>
                    <div className="text-[10px] text-emerald-400 font-semibold pt-1 flex items-center gap-1">
                      <span>{selectedLanguage === 'hi' ? 'क्लिक करें: कोडिंग लैपटॉप ➔' : 'Try: Coding laptops ➔'}</span>
                    </div>
                  </div>

                  <div 
                    className="p-4 bg-[#0A0A0A]/60 hover:bg-zinc-900/60 border border-zinc-800/60 hover:border-indigo-500/50 rounded-2xl space-y-2 cursor-pointer transition-all hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-md group"
                    onClick={() => handleSamplePromptClick(selectedLanguage === 'hi' ? '2000 के अंदर boAt वायरलेस ईयरबड्स' : 'Best boAt earbuds under 2000')}
                  >
                    <Headphones size={16} className="text-indigo-400 group-hover:scale-110 transition-transform" />
                    <h3 className="text-xs font-bold text-white group-hover:text-indigo-300 transition-colors">
                      {selectedLanguage === 'hi' ? 'टॉप ऑडियो डील्स' : 'Top Audio & Earbuds'}
                    </h3>
                    <p className="text-[10px] text-textSecondary leading-normal">
                      {selectedLanguage === 'hi' ? 'कम बजट में बेस्ट वायरलेस ईयरबड्स और हेडफोन्स।' : 'Curated wireless earbuds with best battery and sound quality.'}
                    </p>
                    <div className="text-[10px] text-indigo-400 font-semibold pt-1 flex items-center gap-1">
                      <span>{selectedLanguage === 'hi' ? 'क्लिक करें: boAt ईयरबड्स ➔' : 'Try: boAt earbuds ➔'}</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              // Message Dialog list
              <div className="space-y-8 relative z-10">
                {activeChat.messages.map((msg, index) => {
                  const isUser = msg.role === 'user';
                  const isSpeaking = speakingMessageId === msg.id;

                  return (
                    <div 
                      key={msg.id || index}
                      className={`flex gap-4 max-w-[85%] ${isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}
                    >
                      {/* Avatar */}
                      <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 border border-zinc-800
                        ${isUser ? 'bg-indigo-600 border-indigo-500 text-white font-bold' : 'bg-[#171717] text-zinc-200'}
                      `}>
                        {isUser ? 'A' : <ShoppingBag size={16} />}
                      </div>

                      {/* Content block */}
                      <div className="space-y-2 min-w-0 flex-1">
                        <div className={`
                          p-5 text-sm leading-relaxed shadow-xl border backdrop-blur-sm relative group
                          ${isUser ? 'bg-userMessage/85 border-indigo-500/20 text-white rounded-3xl rounded-tr-sm' : 'bg-aiMessage/85 border-zinc-800/80 text-textPrimary rounded-3xl rounded-tl-sm'}
                        `}>
                          
                          {/* Text-to-Speech Button on Assistant Messages */}
                          {!isUser && (
                            <button 
                              onClick={() => toggleSpeakText(msg.id || `msg-${index}`, msg.content)}
                              className={`absolute top-4 right-4 p-1.5 rounded-lg border transition-all ${
                                isSpeaking 
                                  ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/30 animate-pulse' 
                                  : 'bg-zinc-900/60 text-zinc-400 hover:text-white border-zinc-800 hover:bg-zinc-800'
                              }`}
                              title={isSpeaking ? "Stop Voice Playback" : "Listen in Voice (Audio TTS)"}
                            >
                              {isSpeaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
                            </button>
                          )}

                          {/* Optional user message snapshot */}
                          {msg.image && (
                            <div className="mb-4 rounded-xl overflow-hidden border border-zinc-800 max-w-[280px] hover:scale-[1.02] transition-all">
                              <img src={msg.image} alt="User visual snap" className="w-full h-auto block" />
                            </div>
                          )}

                          {/* Markdown parsing inline */}
                          <div className="whitespace-pre-wrap space-y-3 pr-6">
                            {(msg.content || '').replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*\*/g, '').split('\n').map((line, lineIdx) => {
                              if (line.startsWith('- ') || line.startsWith('* ')) {
                                return (
                                  <div key={lineIdx} className="flex items-start gap-2 pl-2">
                                    <span className="text-indigo-400 mt-1.5">•</span>
                                    <span>{line.substring(2)}</span>
                                  </div>
                                );
                              }
                              if (line.match(/^\d+\.\s/)) {
                                return (
                                  <div key={lineIdx} className="flex items-start gap-2 pl-2">
                                    <span className="text-indigo-400 font-bold mt-0.5">{line.match(/^\d+/)[0]}.</span>
                                    <span>{line.replace(/^\d+\.\s/, '')}</span>
                                  </div>
                                );
                              }
                              return <p key={lineIdx}>{line}</p>;
                            })}
                          </div>

                          {/* ── RICH VIEW 1: PRODUCT GRID ── */}
                          {!isUser && msg.componentType === 'grid' && msg.products && (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-6">
                              {msg.products.map((prod, pidx) => {
                                const wishlisted = isItemWishlisted(prod);
                                const matKey     = prod.title;
                                const matEntry   = materialCache[matKey];

                                // Build the "Ask AI about material" handler
                                const handleAskMaterial = (part, material) => {
                                  const context = getMinimalProductContext(prod);
                                  const question = `Tell me about ${material} used for the ${part} in ${context}. What are its key properties, benefits, and tradeoffs?`;
                                  setInputMessage(question);
                                  setTimeout(() => textareaRef.current?.focus(), 100);
                                };

                                return (
                                  <div 
                                    key={pidx}
                                    className="bg-chatSurface/80 backdrop-blur-md border border-zinc-800 rounded-2xl overflow-hidden flex flex-col p-4 space-y-3 transition-all hover:-translate-y-1 hover:shadow-2xl hover:border-zinc-700"
                                  >
                                    {/* Thumbnail container */}
                                    <ProductImage product={prod} aspect="aspect-square">
                                      <span className="absolute top-2.5 left-2.5 bg-black/60 backdrop-blur-md border border-zinc-800 text-[9px] font-bold text-zinc-300 px-2 py-0.5 rounded-md pointer-events-none z-10">
                                        {prod.source}
                                      </span>
                                      
                                      {/* Wishlist Heart Toggle */}
                                      <button 
                                        className="absolute top-2.5 right-2.5 w-8 h-8 bg-black/70 backdrop-blur-md rounded-full flex items-center justify-center text-zinc-400 hover:text-rose-500 transition-all border border-zinc-800 z-10"
                                        onClick={(e) => toggleWishlist(e, prod)}
                                        title={wishlisted ? "Remove from Wishlist" : "Save to Wishlist"}
                                      >
                                        <Heart 
                                          size={14} 
                                          fill={wishlisted ? '#EF4444' : 'none'} 
                                          className={wishlisted ? 'text-rose-500 scale-110' : ''} 
                                        />
                                      </button>

                                      {/* Material analysis trigger badge on thumbnail */}
                                      {!matEntry && (
                                        <button
                                          className="absolute bottom-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-md bg-black/70 border border-indigo-500/20 text-indigo-300 text-[8px] font-bold hover:bg-indigo-950/60 transition-all z-10"
                                          onClick={() => fetchMaterials(prod)}
                                          title="Load material breakdown"
                                        >
                                          <Layers size={9} />
                                          Materials
                                        </button>
                                      )}
                                    </ProductImage>

                                    {/* Specifications */}
                                    <div className="flex-1 flex flex-col justify-between">
                                      <div>
                                        <span className="text-[9px] font-bold tracking-widest text-indigo-400 uppercase">{prod.brand}</span>
                                        <h4 className="text-xs font-bold text-white line-clamp-2 min-h-[32px] mt-1">{prod.title}</h4>
                                        
                                        {/* Ratings */}
                                        {prod.rating && (
                                          <div className="flex items-center gap-1.5 mt-2">
                                            <div className="flex text-yellow-500 text-[10px]">
                                              {'★'.repeat(Math.round(prod.rating))}
                                              {'☆'.repeat(5 - Math.round(prod.rating))}
                                            </div>
                                            <span className="text-[10px] text-zinc-400">({prod.reviews})</span>
                                          </div>
                                        )}

                                        {/* ── MATERIAL BREAKDOWN ── */}
                                        <div className="pb-1">
                                          <MaterialSection
                                            product={prod}
                                            compact={true}
                                            onAskAI={handleAskMaterial}
                                          />
                                        </div>
                                      </div>

                                      {/* Pricing & Visit Action */}
                                      <div className="pt-3 border-t border-zinc-800/40 mt-3 flex items-end justify-between">
                                        <div>
                                          <div className="flex items-center gap-2">
                                            <span className="text-sm font-black text-emerald-400">{prod.price_inr}</span>
                                            <span className="text-[9px] text-zinc-500 line-through">{prod.mrp_inr}</span>
                                          </div>
                                          {prod.discount && (
                                            <span className="text-[9px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-1 py-0.5 rounded font-black mt-1 inline-block">
                                              {prod.discount}
                                            </span>
                                          )}
                                        </div>

                                        <div className="flex gap-1.5 flex-shrink-0">
                                          <button 
                                            className="px-2.5 h-8 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 text-[10px] font-bold rounded-lg flex items-center justify-center transition-all"
                                            onClick={() => setQuickViewProduct(prod)}
                                            title="Quick View Details"
                                          >
                                            Specs
                                          </button>
                                          {prod.link && (
                                            <a 
                                              href={prod.link} 
                                              target="_blank" 
                                              rel="noopener noreferrer" 
                                              onClick={triggerConfetti}
                                              className="px-3 h-8 bg-emerald-500 hover:bg-emerald-400 text-white text-[10px] font-black rounded-lg flex items-center justify-center gap-1 transition-all shadow-md shadow-emerald-500/10"
                                            >
                                              <span>Buy</span>
                                              <ExternalLink size={10} />
                                            </a>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          {/* ── RICH VIEW 2: COMPARISON TABLE ── */}
                          {!isUser && msg.componentType === 'comparison' && msg.comparisonData && Array.isArray(msg.comparisonData.products) && msg.comparisonData.products.length > 0 && (
                            <div className="mt-6 border border-zinc-800/60 rounded-2xl overflow-hidden bg-chatSurface/80 backdrop-blur-md shadow-2xl">
                              <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse text-xs">
                                  <thead>
                                    <tr className="border-b border-zinc-800/60 bg-black/40">
                                      <th className="p-4 font-bold text-zinc-400">Specifications</th>
                                      {msg.comparisonData.products.map((p, idx) => (
                                        <th key={idx} className={`p-4 font-bold relative ${p.isWinner ? 'text-indigo-400' : 'text-zinc-300'}`}>
                                          <span className="flex items-center gap-1.5">
                                            {p.name}
                                            {p.isWinner && (
                                              <span className="text-[9px] bg-yellow-500/10 border border-yellow-500/20 text-yellow-500 px-1 py-0.5 rounded font-bold flex items-center gap-0.5">
                                                <Award size={9} /> Winner
                                              </span>
                                            )}
                                          </span>
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {msg.comparisonData.features.map((feature, fIdx) => (
                                      <tr key={fIdx} className="border-b border-zinc-800/30 hover:bg-[#121214]/60 transition-all">
                                        <td className="p-4 font-semibold text-zinc-400">{feature}</td>
                                        {msg.comparisonData.products.map((p, pIdx) => (
                                          <td key={pIdx} className={`p-4 font-medium ${p.isWinner ? 'bg-indigo-600/5' : ''}`}>
                                            <div className="flex items-center gap-2">
                                              {p.checks && p.checks[fIdx] ? (
                                                <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0" />
                                              ) : (
                                                <XCircle size={13} className="text-zinc-500 flex-shrink-0" />
                                              )}
                                              <span className={p.isWinner && feature === 'Value Rating' ? 'text-indigo-400 font-extrabold' : 'text-zinc-200'}>
                                                {p.values ? p.values[fIdx] : 'N/A'}
                                              </span>
                                            </div>
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                              
                              {msg.comparisonData.verdict && (
                                <div className="p-4 bg-black/20 border-t border-zinc-800/40 flex items-start gap-2.5">
                                  <Award size={18} className="text-yellow-500 flex-shrink-0 mt-0.5" />
                                  <p className="text-zinc-400 text-xs italic leading-relaxed">
                                    {msg.comparisonData.verdict}
                                  </p>
                                </div>
                              )}
                            </div>
                          )}

                        </div>
                        
                        {/* Message Meta Info */}
                        <div className={`text-[10px] text-zinc-500 px-2 flex items-center gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
                          <span>{isUser ? 'Aryan Nagdev' : 'Stellar Assistant'}</span>
                          <span>•</span>
                          <span>{msg.timestamp}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Shimmer / Typing Spinner */}
                {isTyping && (
                  <div className="flex gap-4 max-w-[85%]">
                    <div className="w-9 h-9 rounded-full bg-aiMessage border border-zinc-800 flex items-center justify-center flex-shrink-0 text-zinc-300 shadow-lg">
                      <ShoppingBag size={16} className="animate-bounce" />
                    </div>
                    <div className="flex items-center pl-2">
                      <div className="p-4 bg-aiMessage/90 border border-zinc-800/80 rounded-3xl rounded-tl-sm flex items-center justify-center shadow-2xl backdrop-blur-md">
                        <div className="relative w-12 h-12 flex items-center justify-center">
                          <div className="absolute inset-[-4px] rounded-full border border-dashed border-zinc-700/50 animate-[spin_8s_linear_infinite]"></div>
                          <div className="absolute inset-[-8px] rounded-full border border-indigo-500/10 animate-[pulse_3s_infinite]"></div>
                          <div className="w-12 h-12 bg-zinc-900/50 border border-zinc-800/60 rounded-xl flex items-center justify-center flex-shrink-0 shadow-inner relative">
                            {loadingStep === 0 && <Shirt className="text-indigo-400 animate-pulse" size={22} />}
                            {loadingStep === 1 && <Laptop className="text-amber-400 animate-pulse" size={22} />}
                            {loadingStep === 2 && <Headphones className="text-zinc-300 animate-pulse" size={22} />}
                            {loadingStep === 3 && <ShoppingBag className="text-rose-400 animate-pulse" size={22} />}
                            {loadingStep === 4 && <Sparkles className="text-yellow-400 animate-pulse" size={22} />}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              </div>
            )}

            <div ref={chatEndRef} />
          </div>
        </div>

        {/* ── INPUT BAR & VOICE RECORDING CONTROLS ── */}
        <div className="p-4 md:p-6 bg-gradient-to-t from-background via-background/80 to-transparent border-t border-zinc-800/30">
          <div className="max-w-[780px] mx-auto space-y-4">
            
            {/* Visual Search upload slot */}
            {imagePreview && (
              <div className="flex items-center gap-3 bg-[#171717]/80 backdrop-blur-md border border-zinc-800 p-2 rounded-2xl w-fit shadow-2xl">
                <img src={imagePreview} alt="Snapshot attachment" className="w-10 h-10 object-cover rounded-lg border border-zinc-800" />
                <div className="flex flex-col min-w-0">
                  <span className="text-[10px] font-bold text-white">Visual Scan Attached</span>
                  <span className="text-[8px] text-zinc-500">Scan via Stellar Vision</span>
                </div>
                <button className="text-zinc-500 hover:text-white p-1 rounded-full hover:bg-zinc-800" onClick={() => setImagePreview(null)}>
                  <X size={12} />
                </button>
              </div>
            )}

            {/* Input Bar */}
            <div className="flex items-end gap-3 bg-[#171717]/70 backdrop-blur-md border border-zinc-800/80 rounded-3xl p-3 shadow-2xl focus-within:border-indigo-500 transition-all">
              
              {/* Voice Input Mic Button */}
              <button 
                className={`w-10 h-10 rounded-2xl flex items-center justify-center transition-all ${
                  isListening 
                    ? 'bg-rose-600 text-white shadow-lg shadow-rose-600/40 animate-pulse' 
                    : 'bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 hover:text-white'
                }`}
                onClick={isListening ? stopVoiceInput : startVoiceInput}
                title={isListening ? "Stop Voice Recording" : `Speak in ${selectedLanguage === 'hi' ? 'Hindi (हिन्दी)' : 'Voice'}`}
              >
                {isListening ? <MicOff size={18} /> : <Mic size={18} />}
              </button>

              <div className="flex-1 min-w-0 pb-1 pl-2 flex items-center min-h-[40px]">
                <textarea 
                  ref={textareaRef}
                  rows={1}
                  placeholder={
                    selectedLanguage === 'hi'
                      ? "कुछ भी पूछें... 20000 के अंदर बेस्ट फोन या boAt और Noise की तुलना करें?"
                      : selectedLanguage === 'hinglish'
                      ? "Kuch bhi pucho... Best laptop under 60k ya budget earbuds batao?"
                      : "Ask anything... Best laptop under 70k or show me boAt earbuds?"
                  }
                  className="w-full bg-transparent border-0 outline-none text-sm text-textPrimary placeholder-zinc-500 resize-none max-h-32"
                  value={inputMessage}
                  disabled={isTyping}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      if (!isTyping && inputMessage.trim()) {
                        handleSendMessage();
                      }
                    }
                  }}
                />
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button 
                  className="w-10 h-10 rounded-2xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white flex items-center justify-center transition-all shadow-md shadow-indigo-600/20 disabled:shadow-none cursor-pointer disabled:cursor-not-allowed"
                  disabled={isTyping || (!inputMessage.trim() && !imagePreview)}
                  onClick={() => {
                    if (!isTyping && (inputMessage.trim() || imagePreview)) {
                      handleSendMessage();
                    }
                  }}
                  title={isTyping ? "Searching live stores..." : "Send query"}
                >
                  {isTyping ? (
                    <div className="w-4 h-4 rounded-full border-2 border-white/70 border-t-transparent animate-spin" />
                  ) : (
                    <Send size={16} />
                  )}
                </button>
              </div>
            </div>

            {/* Suggestion Chips Below */}
            {/* Dynamic AI suggestions when user is typing */}
            {inputMessage.trim().length >= 4 && (
              <div className="space-y-2">
                {isSuggesting && querySuggestions.length === 0 ? (
                  <div className="flex items-center gap-2 text-zinc-500">
                    <div className="w-3 h-3 rounded-full border border-indigo-500/60 border-t-transparent animate-spin" />
                    <span className="text-[11px]">Understanding your intent...</span>
                  </div>
                ) : querySuggestions.length > 0 ? (
                  <>
                    <div className="flex items-center gap-1.5 text-zinc-500">
                      <Sparkles size={11} className="text-indigo-400" />
                      <span className="text-[10px] font-semibold tracking-wider uppercase">Suggestions</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {querySuggestions.map((suggestion, idx) => (
                        <button
                          key={idx}
                          disabled={isTyping}
                          className="flex-shrink-0 px-3 py-1.5 bg-indigo-950/40 hover:bg-indigo-900/60 border border-indigo-500/30 hover:border-indigo-400/60 text-xs font-medium rounded-full text-indigo-200 hover:text-white transition-all hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-sm shadow-sm shadow-indigo-900/20 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                          onClick={() => {
                            setQuerySuggestions([]);
                            handleSamplePromptClick(suggestion);
                          }}
                        >
                          ✦ {suggestion}
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            )}

            {/* Static suggestion chips – shown only on empty chat with no input */}
            {activeChat.messages.length === 0 && inputMessage.trim().length < 4 && (
              <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
                {currentSuggestions.map((chip, idx) => (
                  <button 
                    key={idx}
                    disabled={isTyping}
                    className="flex-shrink-0 px-4 py-2 bg-[#171717]/60 hover:bg-zinc-800/60 border border-zinc-800/60 hover:border-zinc-700 text-xs font-semibold rounded-full text-zinc-300 hover:text-white transition-all hover:-translate-y-0.5 active:translate-y-0 backdrop-blur-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={() => handleSamplePromptClick(chip.text)}
                  >
                    <span className="mr-1.5">{chip.icon}</span>
                    <span>{chip.text}</span>
                  </button>
                ))}
              </div>
            )}

          </div>
        </div>
      </main>

      {/* ── RIGHT COLLAPSIBLE RECOMMENDATIONS DRAWER ── */}
      <aside className={`
        fixed xl:static inset-y-0 right-0 w-[300px] bg-chatSurface/70 backdrop-blur-md border-l border-zinc-800/40 
        flex flex-col h-full z-45 transition-all xl:translate-x-0
        ${isRightSidebarOpen ? 'translate-x-0' : 'translate-x-full xl:w-0 xl:border-l-0 overflow-hidden'}
      `}>
        <div className="p-4 border-b border-zinc-800/60 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-indigo-500 rounded-full shadow-lg shadow-indigo-500/50"></span>
            <span className="text-sm font-bold text-white">
              {selectedLanguage === 'hi' ? 'लाइव सिफारिशें' : 'Live Recommendations'}
            </span>
          </div>
          <button 
            className="p-1 rounded-lg text-zinc-400 hover:text-white hover:bg-[#171717]/40"
            onClick={() => setIsRightSidebarOpen(false)}
          >
            <X size={15} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {activeChat.products && activeChat.products.length > 0 ? (
            activeChat.products.map((prod, idx) => {
              const wishlisted = isItemWishlisted(prod);
              const matEntry   = materialCache[prod.title];
              const handleSidebarAskMaterial = (part, material) => {
                const context = getMinimalProductContext(prod);
                const question = `Tell me about ${material} used for the ${part} in ${context}. What are its key properties, benefits, and tradeoffs?`;
                setInputMessage(question);
                setTimeout(() => textareaRef.current?.focus(), 100);
              };
              return (
                <div 
                  key={idx}
                  className="bg-aiMessage/80 border border-zinc-800/80 rounded-2xl overflow-hidden flex flex-col p-4 space-y-3 transition-all hover:-translate-y-1 hover:shadow-2xl"
                >
                  <ProductImage product={prod} aspect="aspect-square" containerClassName="bg-[#121214]/60">
                    <span className="absolute top-2 left-2 bg-black/60 backdrop-blur-md border border-zinc-800 text-[8px] font-bold text-zinc-300 px-2 py-0.5 rounded-md pointer-events-none z-10">
                      {prod.source}
                    </span>
                    <button 
                      className="absolute top-2 right-2 w-7 h-7 bg-black/60 backdrop-blur-md rounded-full flex items-center justify-center text-zinc-400 hover:text-rose-500 transition-all border border-zinc-800 z-10"
                      onClick={(e) => toggleWishlist(e, prod)}
                      title={wishlisted ? "Remove from Wishlist" : "Save to Wishlist"}
                    >
                      <Heart size={13} fill={wishlisted ? '#EF4444' : 'none'} className={wishlisted ? 'text-rose-500' : ''} />
                    </button>
                  </ProductImage>

                  <div>
                    <span className="text-[9px] font-bold tracking-widest text-indigo-400 uppercase">{prod.brand}</span>
                    <h4 className="text-xs font-bold text-white line-clamp-2 min-h-[32px] mt-1" title={prod.title}>{prod.title}</h4>
                    
                    {prod.rating && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <div className="flex text-yellow-500 text-[10px]">
                          {'★'.repeat(Math.round(prod.rating))}
                          {'☆'.repeat(5 - Math.round(prod.rating))}
                        </div>
                        <span className="text-[9px] text-zinc-400">({prod.reviews})</span>
                      </div>
                    )}

                    {/* ── SIDEBAR COMPACT MATERIAL STRIP ── */}
                    {!matEntry && (
                      <button
                        onClick={() => fetchMaterials(prod)}
                        className="mt-2 flex items-center gap-1 text-[8px] text-indigo-400 hover:text-indigo-300 font-bold transition-colors"
                      >
                        <Layers size={9} />
                        View Materials
                      </button>
                    )}
                    <MaterialSection
                      product={prod}
                      compact={true}
                      onAskAI={handleSidebarAskMaterial}
                    />
                  </div>

                  <div className="pt-3 border-t border-zinc-800/40 flex flex-col gap-2.5">
                    <div className="flex justify-between items-center">
                      <span className="text-[8px] text-zinc-500 uppercase font-black">Price</span>
                      <span className="text-sm font-black text-emerald-400">{prod.price_inr}</span>
                    </div>

                    <div className="flex gap-1.5">
                      <button 
                        className="flex-1 h-9 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl text-xs font-bold flex items-center justify-center gap-1 transition-all"
                        onClick={() => setQuickViewProduct(prod)}
                      >
                        <Eye size={13} />
                        <span>Specs</span>
                      </button>
                      {prod.link && (
                        <a 
                          href={prod.link} 
                          target="_blank" 
                          rel="noopener noreferrer" 
                          onClick={triggerConfetti}
                          className="flex-1 h-9 bg-emerald-500 hover:bg-emerald-400 text-white rounded-xl text-xs font-black flex items-center justify-center gap-1 transition-all shadow-md shadow-emerald-500/20"
                        >
                          <span>Buy</span>
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="py-12 text-center text-zinc-500 space-y-4">
              <ShoppingBag size={36} className="mx-auto opacity-30 animate-pulse" />
              <div className="space-y-1">
                <h5 className="text-xs font-bold text-white">
                  {selectedLanguage === 'hi' ? 'कोई सक्रिय उत्पाद नहीं' : 'No active matches'}
                </h5>
                <p className="text-[10px] text-zinc-600 max-w-[180px] mx-auto leading-relaxed">
                  {selectedLanguage === 'hi'
                    ? 'खोजने पर अनुशंसित उत्पाद यहाँ प्रदर्शित होंगे।'
                    : 'Recommended products will pop up here as you talk to Stellar.'}
                </p>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* ── GLOBAL WISHLIST MODAL / DRAWER (LOCAL STORAGE) ── */}
      {isWishlistOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-[9999] flex items-center justify-center animate-fade-in" onClick={() => setIsWishlistOpen(false)}>
          <div className="bg-chatSurface border border-zinc-800 rounded-3xl w-full max-w-2xl max-h-[85vh] mx-4 overflow-hidden shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
            
            {/* Wishlist Header */}
            <div className="p-5 border-b border-zinc-800/80 flex items-center justify-between bg-black/40">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-500">
                  <Heart size={20} fill="#EF4444" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-white">
                    {selectedLanguage === 'hi' ? 'मेरी विशलिस्ट (Saved Products)' : 'My Saved Wishlist'}
                  </h3>
                  <span className="text-[11px] text-zinc-400">
                    {wishlist.length} {wishlist.length === 1 ? 'item' : 'items'} saved in browser memory (LocalStorage)
                  </span>
                </div>
              </div>
              <button className="text-zinc-500 hover:text-white p-2" onClick={() => setIsWishlistOpen(false)}>
                <X size={20} />
              </button>
            </div>

            {/* Wishlist Items List */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {wishlist.length === 0 ? (
                <div className="py-16 text-center space-y-4">
                  <div className="w-16 h-16 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-600 mx-auto">
                    <Heart size={28} />
                  </div>
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-white">
                      {selectedLanguage === 'hi' ? 'आपकी विशलिस्ट खाली है' : 'Your wishlist is empty'}
                    </h4>
                    <p className="text-xs text-zinc-500 max-w-xs mx-auto">
                      {selectedLanguage === 'hi' 
                        ? 'उत्पाद कार्ड पर हार्ट (❤️) आइकन दबाकर अपने पसंदीदा उत्पादों को सेव करें।'
                        : 'Click the heart icon on any product card to bookmark and save it directly in your browser.'}
                    </p>
                  </div>
                </div>
              ) : (
                wishlist.map((item, index) => (
                  <div 
                    key={index}
                    className="p-4 bg-[#171717]/80 border border-zinc-800 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 hover:border-zinc-700 transition-all"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <ProductImage 
                        product={item} 
                        aspect="w-16 h-16" 
                        compact={true} 
                        className="w-16 h-16 object-cover rounded-xl"
                        containerClassName="w-16 h-16 rounded-xl flex-shrink-0"
                      />
                      <div className="min-w-0">
                        <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider">{item.brand}</span>
                        <h4 className="text-xs font-bold text-white line-clamp-1" title={item.title}>{item.title}</h4>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs font-extrabold text-emerald-400">{item.price_inr}</span>
                          <span className="text-[10px] text-zinc-500">• {item.source}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                      {item.link && item.link !== '#' && (
                        <a 
                          href={item.link} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          onClick={triggerConfetti}
                          className="px-3.5 py-2 bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 transition-all shadow-md shadow-emerald-500/10"
                        >
                          <span>Buy</span>
                          <ExternalLink size={12} />
                        </a>
                      )}
                      <button 
                        onClick={() => removeFromWishlist(item)}
                        className="p-2 text-zinc-500 hover:text-rose-500 hover:bg-rose-950/20 rounded-xl transition-all"
                        title="Remove from wishlist"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Wishlist Footer */}
            {wishlist.length > 0 && (
              <div className="p-5 border-t border-zinc-800/80 bg-black/40 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div>
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block">
                    {selectedLanguage === 'hi' ? 'कुल अनुमानित मूल्य' : 'Total Estimated Cost'}
                  </span>
                  <span className="text-lg font-black text-emerald-400">
                    ₹{totalWishlistValue.toLocaleString('en-IN')}
                  </span>
                </div>

                <div className="flex items-center gap-3 w-full sm:w-auto">
                  <button 
                    onClick={() => {
                      const titles = wishlist.slice(0, 2).map(w => w.title).join(' vs ');
                      setIsWishlistOpen(false);
                      handleSendMessage(`Compare my wishlist items: ${titles}`);
                    }}
                    className="flex-1 sm:flex-initial px-4 py-2.5 bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-300 text-xs font-bold rounded-xl transition-all"
                  >
                    Compare in Chat
                  </button>
                  <button 
                    onClick={clearWishlist}
                    className="px-4 py-2.5 bg-rose-950/20 hover:bg-rose-950/40 border border-rose-900/30 text-rose-400 text-xs font-bold rounded-xl transition-all"
                  >
                    Clear All
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      )}

      {/* ── LIVE VOICE RECORDING OVERLAY / EQUALIZER MODAL ── */}
      {isListening && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-[9999] flex items-center justify-center animate-fade-in">
          <div className="bg-chatSurface border border-zinc-800 rounded-3xl p-8 max-w-sm w-full mx-4 text-center space-y-6 shadow-2xl">
            <div className="w-16 h-16 bg-indigo-600/10 border border-indigo-500/30 text-indigo-400 rounded-full flex items-center justify-center mx-auto shadow-2xl animate-pulse">
              <Mic size={28} />
            </div>
            <div className="space-y-2">
              <h3 className="text-lg font-bold text-white">
                {selectedLanguage === 'hi' ? 'बोलिए, मैं सुन रहा हूँ...' : 'Listening for shopping cues...'}
              </h3>
              <p className="text-xs text-zinc-400 italic min-h-[20px]">
                {voiceTranscript ? `"${voiceTranscript}"` : (selectedLanguage === 'hi' ? '"20000 के अंदर सबसे अच्छा फोन..."' : '"Compare prestige and hawkins cooker under 3000..."')}
              </p>
              <span className="text-[10px] bg-indigo-500/10 text-indigo-400 font-bold px-2 py-0.5 rounded-full inline-block">
                Language: {selectedLanguage === 'hi' ? 'Hindi (hi-IN)' : 'Indian English (en-IN)'}
              </span>
            </div>
            
            {/* Pulsing Audio waveform bar graph */}
            <div className="flex gap-1.5 justify-center items-center h-8">
              <span className="w-1.5 h-3 bg-indigo-500 rounded-full animate-bounce"></span>
              <span className="w-1.5 h-7 bg-emerald-400 rounded-full animate-bounce [animation-delay:0.15s]"></span>
              <span className="w-1.5 h-9 bg-indigo-400 rounded-full animate-bounce [animation-delay:0.3s]"></span>
              <span className="w-1.5 h-6 bg-zinc-400 rounded-full animate-bounce [animation-delay:0.2s]"></span>
              <span className="w-1.5 h-3 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.4s]"></span>
            </div>

            <div className="flex gap-3">
              <button 
                onClick={stopVoiceInput}
                className="flex-1 py-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-bold text-xs rounded-2xl transition-all"
              >
                Cancel
              </button>
              <button 
                onClick={() => {
                  stopVoiceInput();
                  if (voiceTranscript.trim()) {
                    handleSendMessage(voiceTranscript);
                  }
                }}
                className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-2xl transition-all shadow-lg shadow-indigo-600/30"
              >
                Send Voice
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── SETTINGS AND SPECS DIALOG ── */}
      {isSettingsOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[9999] flex items-center justify-center animate-fade-in" onClick={() => setIsSettingsOpen(false)}>
          <div className="bg-chatSurface border border-zinc-800 rounded-3xl w-full max-w-md mx-4 overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="p-5 border-b border-zinc-800/80 flex items-center justify-between bg-black/20">
              <span className="text-sm font-bold text-white">Settings & Preferences</span>
              <button className="text-zinc-500 hover:text-white" onClick={() => setIsSettingsOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-6">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Default Language</label>
                <select 
                  className="w-full bg-[#171717] border border-zinc-800 rounded-xl px-4 py-3 text-xs text-white outline-none cursor-pointer focus:border-indigo-500"
                  value={selectedLanguage}
                  onChange={(e) => {
                    setSelectedLanguage(e.target.value);
                    showToast(`Language set to ${e.target.value.toUpperCase()}`);
                  }}
                >
                  <option value="en">English (India / Global)</option>
                  <option value="hi">हिंदी (Hindi)</option>
                  <option value="hinglish">Hinglish (Hindi in English Script)</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">LLM & Search Core</label>
                <select 
                  className="w-full bg-[#171717] border border-zinc-800 rounded-xl px-4 py-3 text-xs text-white outline-none cursor-pointer focus:border-indigo-500"
                  value={selectedModel}
                  onChange={(e) => {
                    setSelectedModel(e.target.value);
                    showToast(`Switched back-end LLM index to ${e.target.value}`);
                  }}
                >
                  <option>Stellar AI • Groq Llama 3.3 70B (Recommended)</option>
                  <option>MiniLM SLM + FAISS India Vector Store</option>
                  <option>SerpAPI Google Shopping India</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-3.5 bg-[#171717] rounded-xl border border-zinc-800">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase block mb-1">Local Storage</span>
                  <span className="font-semibold text-emerald-400">Wishlist & History</span>
                </div>
                <div className="p-3.5 bg-[#171717] rounded-xl border border-zinc-800">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase block mb-1">Currencies</span>
                  <span className="font-semibold text-white">INR (₹) Realtime</span>
                </div>
              </div>

              <button 
                onClick={() => {
                  setConversations([{
                    id: `chat-${Date.now()}`,
                    title: selectedLanguage === 'hi' ? 'नई बातचीत' : 'New Conversation',
                    messages: [],
                    products: []
                  }]);
                  setIsSettingsOpen(false);
                  showToast("Cleared active chat sessions");
                }}
                className="w-full py-3.5 bg-rose-950/20 hover:bg-rose-950/40 border border-rose-900/30 hover:border-rose-500/20 rounded-xl text-rose-400 font-bold text-xs transition-all active:scale-[0.98]"
              >
                Clear Conversation History
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── QUICK VIEW PRODUCT INSPECTOR MODAL ── */}
      {quickViewProduct && (() => {
        const qvMatEntry = materialCache[quickViewProduct.title];
        const qvMats     = qvMatEntry?.data || [];
        const handleQVAskMaterial = (part, material) => {
          setQuickViewProduct(null);
          const context = getMinimalProductContext(quickViewProduct);
          const question = `Tell me about ${material} used for the ${part} in ${context}. What are its key properties, benefits, and tradeoffs?`;
          setInputMessage(question);
          setTimeout(() => textareaRef.current?.focus(), 150);
        };
        return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-[9999] flex items-center justify-center animate-fade-in" onClick={() => setQuickViewProduct(null)}>
          <div
            className="bg-chatSurface border border-zinc-800 rounded-3xl w-full max-w-2xl mx-4 overflow-hidden shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
            style={{ maxHeight: '90vh' }}
          >
            {/* Top: image + core info row */}
            <div className="flex flex-col md:flex-row">
              {/* Image panel */}
              <div className="md:w-2/5 relative bg-[#121214]/60 flex items-center justify-center border-b md:border-b-0 md:border-r border-zinc-800 p-6 flex-shrink-0">
                <ProductImage 
                  product={quickViewProduct} 
                  aspect="aspect-square" 
                  className="w-full h-full object-cover rounded-2xl"
                  containerClassName="w-full aspect-square rounded-2xl"
                >
                  <span className="absolute top-4 left-4 bg-black/60 border border-zinc-800 text-[10px] font-bold text-white px-2 py-0.5 rounded-lg z-10">
                    {quickViewProduct.source}
                  </span>
                </ProductImage>
              </div>

              {/* Spec details */}
              <div className="md:w-3/5 p-6 flex flex-col justify-between space-y-4 overflow-y-auto">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest">{quickViewProduct.brand}</span>
                    <button className="text-zinc-500 hover:text-white" onClick={() => setQuickViewProduct(null)}>
                      <X size={18} />
                    </button>
                  </div>
                  <h3 className="text-sm font-black text-white mt-2 leading-relaxed">{quickViewProduct.title}</h3>
                  
                  {quickViewProduct.rating && (
                    <div className="flex items-center gap-1.5 mt-3">
                      <div className="flex text-yellow-500 text-[11px]">
                        {'★'.repeat(Math.round(quickViewProduct.rating))}
                        {'☆'.repeat(5 - Math.round(quickViewProduct.rating))}
                      </div>
                      <span className="text-xs font-bold text-white">{quickViewProduct.rating}</span>
                      <span className="text-xs text-zinc-500">({quickViewProduct.reviews} reviews)</span>
                    </div>
                  )}

                  <div className="mt-3 p-3 bg-[#171717] rounded-xl border border-zinc-800/80 space-y-1">
                    <span className="text-[9px] font-bold text-zinc-500 uppercase block">Availability</span>
                    <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                      <CheckCircle2 size={13} /> In stock on {quickViewProduct.source || 'Indian Stores'}
                    </span>
                  </div>
                </div>

                <div>
                  <div className="flex justify-between items-center mb-3">
                    <div>
                      <span className="text-[9px] font-bold text-zinc-500 uppercase block">Current Price</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xl font-black text-emerald-400">{quickViewProduct.price_inr}</span>
                        {quickViewProduct.mrp_inr && (
                          <span className="text-xs text-zinc-500 line-through">{quickViewProduct.mrp_inr}</span>
                        )}
                      </div>
                    </div>
                    {quickViewProduct.discount && (
                      <span className="text-xs bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-bold px-2 py-0.5 rounded-lg">
                        {quickViewProduct.discount}
                      </span>
                    )}
                  </div>

                  <div className="flex gap-2">
                    <button 
                      onClick={(e) => toggleWishlist(e, quickViewProduct)}
                      className="p-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-rose-400 rounded-2xl flex items-center justify-center transition-all border border-zinc-700"
                      title="Save to Wishlist"
                    >
                      <Heart size={16} fill={isItemWishlisted(quickViewProduct) ? '#EF4444' : 'none'} className={isItemWishlisted(quickViewProduct) ? 'text-rose-500' : ''} />
                    </button>

                    {quickViewProduct.link && (
                      <a 
                        href={quickViewProduct.link} 
                        target="_blank" 
                        rel="noopener noreferrer" 
                        onClick={() => {
                          triggerConfetti();
                          setQuickViewProduct(null);
                        }}
                        className="flex-1 py-3 bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-black rounded-2xl flex items-center justify-center gap-2 transition-all hover:-translate-y-0.5 shadow-lg shadow-emerald-500/20 text-center"
                      >
                        <ExternalLink size={14} />
                        <span>Visit Website to Buy</span>
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* ── MATERIAL & BUILD SPECIFICATIONS PANEL ── */}
            <div className="border-t border-zinc-800/60 p-5 bg-gradient-to-b from-zinc-950/60 to-black/80">
              <div className="flex items-center justify-between mb-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                    <ShieldCheck size={16} className="text-indigo-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-bold text-white tracking-wide uppercase">Material & Build</h4>
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-zinc-800/80 text-zinc-300 border border-zinc-700/50">
                        Specifications
                      </span>
                    </div>
                    <p className="text-[10px] text-zinc-400">Key construction materials, structural chassis & protective elements</p>
                  </div>
                </div>
                {!qvMatEntry && (
                  <button
                    onClick={() => fetchMaterials(quickViewProduct)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] font-bold shadow-lg shadow-indigo-600/30 transition-all"
                  >
                    <Atom size={12} className="animate-spin" style={{ animationDuration: '3s' }} />
                    Analyze Build
                  </button>
                )}
              </div>

              {/* Loading shimmer */}
              {qvMatEntry?.status === 'loading' && (
                <div className="space-y-2 rounded-xl border border-zinc-800/60 p-3 bg-zinc-900/30">
                  <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                    <Atom size={12} className="text-indigo-400 animate-spin" />
                    <span>Analyzing product architecture and component materials...</span>
                  </div>
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-8 w-full bg-zinc-800/40 rounded-lg animate-pulse" style={{ animationDelay: `${i * 0.12}s` }} />
                  ))}
                </div>
              )}

              {/* E-Commerce Structured Specifications Table */}
              {qvMats.length > 0 && (
                <div className="rounded-xl border border-zinc-800/70 bg-zinc-900/40 divide-y divide-zinc-800/50 overflow-hidden shadow-sm">
                  {qvMats.map((m, i) => (
                    <div
                      key={i}
                      onClick={() => handleQVAskMaterial(m.part, m.material)}
                      className="flex flex-col sm:flex-row sm:items-center justify-between px-3.5 py-2.5 hover:bg-zinc-800/50 transition-colors gap-1 sm:gap-3 group/spec cursor-pointer"
                      title={`Ask AI about ${m.material} (${m.part})`}
                    >
                      {/* Attribute / Component Name */}
                      <div className="sm:w-1/3 shrink-0 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0"></span>
                        <span className="text-xs font-medium text-zinc-400">
                          {m.part}
                        </span>
                      </div>

                      {/* Material Value & Description */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold text-white tracking-tight">
                            {m.material}
                          </span>
                          {m.confidence === 'high' && (
                            <span className="text-[8px] font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-500/25 px-1.5 py-0.5 rounded">
                              Verified Spec
                            </span>
                          )}
                        </div>
                        {m.description && (
                          <p className="text-[10px] text-zinc-400 leading-relaxed mt-0.5 font-normal">
                            {m.description}
                          </p>
                        )}
                      </div>

                      {/* Ask AI action button */}
                      <div className="shrink-0 pt-1 sm:pt-0">
                        <button
                          onClick={() => handleQVAskMaterial(m.part, m.material)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-indigo-600/30 text-zinc-300 hover:text-indigo-200 border border-zinc-700/60 hover:border-indigo-500/40 text-[10px] font-semibold transition-all"
                          title={`Ask AI about ${m.material}`}
                        >
                          <MessageCircle size={10} className="text-indigo-400" />
                          <span>Ask AI</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Prompt to load materials if not yet fetched */}
              {!qvMatEntry && (
                <div className="flex items-center justify-between p-3.5 bg-zinc-900/40 rounded-xl border border-zinc-800/60">
                  <div className="flex items-center gap-3">
                    <Atom size={16} className="text-indigo-400 flex-shrink-0" />
                    <p className="text-xs text-zinc-400">
                      View detailed body, frame, display glass, and component material breakdown for this product.
                    </p>
                  </div>
                  <button
                    onClick={() => fetchMaterials(quickViewProduct)}
                    className="shrink-0 ml-3 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-bold transition-all shadow-md shadow-indigo-600/20"
                  >
                    Load Specs
                  </button>
                </div>
              )}

              {/* Subtle footer tip */}
              {qvMats.length > 0 && (
                <div className="mt-2.5 flex items-center justify-between text-[10px] text-zinc-500">
                  <span className="flex items-center gap-1">
                    <Info size={11} className="text-zinc-500" />
                    Specifications dynamically mapped from verified hardware and apparel records.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
        );
      })()}

      {/* ── TOAST ALERT ── */}
      {toast.visible && (
        <div className="fixed bottom-6 right-6 bg-[#171717]/95 border border-zinc-800 border-l-4 border-l-emerald-500 rounded-xl shadow-2xl p-4 flex items-center gap-3 z-[9999] animate-fade-in backdrop-blur-md">
          <Sparkles size={18} className="text-emerald-400" />
          <span className="text-xs font-bold text-white">{toast.message}</span>
        </div>
      )}

    </div>
  );
}

export default App;
