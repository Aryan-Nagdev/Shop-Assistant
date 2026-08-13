"""
conversation_manager.py  –  Stateful Conversational Shopping & Slot Resolution (Phase 3)
────────────────────────────────────────────────────────────────────────────────────────
Maintains active shopping session context across conversational turns.
Handles follow-up modifications:
  1. Budget adjustments ("make it 60k", "under 60k", "change budget to 60000")
  2. Attribute refinements ("only 16GB", "with 16gb ram", "with dedicated graphics")
  3. Attribute removals ("forget the i5 requirement", "without graphics", "any color")
  4. Brand switches ("show me dell instead", "what about lenovo")
  5. Color additions ("black colour", "only black", "in blue")
  6. Category context switching (detects when user starts an entirely new shopping task)
"""
from __future__ import annotations
import re
import copy
from typing import Any
from src.query_understanding import understand, QueryUnderstanding, BRAND_REGISTRY


class ShoppingContext:
    """
    Stateful container representing the user's current shopping criteria.
    """
    __slots__ = (
        'category',
        'audio_type',
        'brand',
        'brands',
        'min_price',
        'max_price',
        'specifications',
        'color',
        'use_case',
        'hard_requirements',
        'soft_preferences',
        'last_query_raw',
        'turn_count',
        'last_intent',             # tracks intent across turns for follow-up routing
        'last_comparison_items',   # stores [BrandA, BrandB] from a comparison turn
    )

    def __init__(self):
        self.category: str | None = None
        self.audio_type: str | None = None
        self.brand: str | None = None
        self.brands: list[str] = []
        self.min_price: int | None = None
        self.max_price: int | None = None
        self.specifications: dict[str, str] = {}
        self.color: str | None = None
        self.use_case: str | None = None
        self.hard_requirements: list[str] = []
        self.soft_preferences: list[str] = []
        self.last_query_raw: str = ""
        self.turn_count: int = 0
        self.last_intent: str | None = None
        self.last_comparison_items: list[str] = []

    def is_empty(self) -> bool:
        return not (self.category or self.audio_type or self.brand or self.brands or self.max_price or self.specifications or self.color)

    def clear(self):
        self.category = None
        self.audio_type = None
        self.brand = None
        self.brands = []
        self.min_price = None
        self.max_price = None
        self.specifications = {}
        self.color = None
        self.use_case = None
        self.hard_requirements = []
        self.soft_preferences = []
        self.last_query_raw = ""
        self.turn_count = 0
        self.last_intent = None
        self.last_comparison_items = []

    def to_dict(self) -> dict[str, Any]:
        return {
            'category':          self.category,
            'audio_type':        self.audio_type,
            'brand':             self.brand,
            'brands':            self.brands,
            'min_price':         self.min_price,
            'max_price':         self.max_price,
            'specifications':    self.specifications,
            'color':             self.color,
            'use_case':          self.use_case,
            'hard_requirements': self.hard_requirements,
            'soft_preferences':  self.soft_preferences,
        }

    def synthesize_effective_query(self) -> str:
        """
        Synthesizes a clean, comprehensive natural search query from current state.
        Example: "Dell laptop Intel i5 16GB RAM 512GB SSD black under Rs.60,000"
        """
        parts = []
        if self.brands:
            parts.append(' vs '.join(self.brands))
        elif self.brand:
            parts.append(self.brand)
        if self.color:
            parts.append(self.color)
        if self.specifications.get('cpu'):
            parts.append(self.specifications['cpu'])
        if self.specifications.get('ram'):
            parts.append(f"{self.specifications['ram']} RAM")
        if self.specifications.get('storage'):
            parts.append(self.specifications['storage'])
        if self.specifications.get('gpu'):
            parts.append(f"{self.specifications['gpu']} graphics")
        if self.specifications.get('anc'):
            parts.append("ANC")
        if self.use_case:
            parts.append(self.use_case)

        cat_term = self.audio_type or self.category or 'product'
        parts.append(cat_term)

        if self.max_price is not None:
            parts.append(f"under Rs.{self.max_price:,}")
        elif self.min_price is not None:
            parts.append(f"above Rs.{self.min_price:,}")

        return ' '.join(parts)


class ConversationManager:
    """
    Manages multi-turn conversation and contextual slot resolution.
    """

    # Price modification trigger patterns
    _PRICE_MOD_RE = re.compile(
        r'\b(?:make\s+it\s+|change\s+(?:the\s+)?(?:budget|price)\s+to\s+|increase\s+(?:the\s+)?(?:budget|price)\s+to\s+|'
        r'reduce\s+(?:the\s+)?(?:budget|price)\s+to\s+|budget\s+(?:is\s+|of\s+)?|max\s+|around\s+|under\s+|below\s+|less\s+than\s+)'
        r'(?:[₹₨$rs\.]*\s*)(\d+k|\d+,\d+|\d+)\b',
        re.I
    )

    # Constraint removal trigger patterns
    _REMOVAL_RE = re.compile(
        r'\b(?:forget|remove|drop|cancel|without|no|ignore|skip)\s+(?:the\s+)?'
        r'(i[3579]|ryzen|cpu|processor|ram|16gb|8gb|graphics|gpu|dedicated\s*gpu|anc|brand|color|colour|budget|price)\b',
        re.I
    )

    # Brand switch patterns
    _BRAND_SWITCH_RE = re.compile(
        r'\b(?:show\s+me|switch\s+to|what\s+about|only|prefer|make\s+it)\s+([a-zA-Z\s\.\-&]+)\s+(?:instead|brand|shoes|phone|laptop)?\b',
        re.I
    )

    def __init__(self):
        self.context = ShoppingContext()

    def process_turn(self, raw_user_msg: str) -> tuple[ShoppingContext, QueryUnderstanding, str]:
        """
        Processes a user turn:
        1. Understands raw input with Phase 1 QueryUnderstanding.
        2. Detects if input is a follow-up modification vs new intent.
        3. Updates ShoppingContext accordingly.
        4. Preserves the user's original query intent while enriching missing context.
        Returns (context, effective_qu, effective_query_str).
        """
        user_msg = raw_user_msg.strip()
        qu_raw = understand(user_msg)

        # ── Check for Comparison Queries (Never corrupt with previous context) ──
        is_comparison = (
            qu_raw.intent == 'comparison'
            or len(qu_raw.brands) >= 2
            or bool(re.search(r'\b(?:vs\.?|versus|compare|compre|comapre|difference\s+between)\b', user_msg, re.I))
            or (qu_raw.brands and bool(re.search(r'\b(?:or|between|better|best)\b', user_msg, re.I)))
        )

        if is_comparison:
            # Clean reset for comparison turn
            self.context.clear()
            self.context.last_intent = 'comparison'
            self.context.last_comparison_items = list(qu_raw.brands)
            self._apply_qu_to_context(qu_raw, user_msg)
            normalized_q = qu_raw.normalized_query if qu_raw.normalized_query else user_msg
            return self.context, qu_raw, normalized_q

        # If context is empty, initialize directly from current query
        if self.context.is_empty():
            self._apply_qu_to_context(qu_raw, user_msg)
            normalized_q = qu_raw.normalized_query if qu_raw.normalized_query else user_msg
            return self.context, qu_raw, normalized_q

        # ── 1. Check if user is starting a completely new category ────────────
        if qu_raw.category and self.context.category and qu_raw.category != self.context.category:
            print(f"[ConversationManager] New category detected: '{qu_raw.category}' (was '{self.context.category}') -> Resetting context")
            self.context.clear()
            self._apply_qu_to_context(qu_raw, user_msg)
            normalized_q = qu_raw.normalized_query if qu_raw.normalized_query else user_msg
            return self.context, qu_raw, normalized_q

        # ── Check if this is a standalone product search / recommendation query ─────
        # If previous turn was comparison, or query has category with (brand/specs/price/use_case), treat as fresh search
        is_standalone = bool(
            (self.context.last_intent == 'comparison' and not re.search(r'\b(?:which\s+one|between\s+(?:them|these)|of\s+(?:the\s+two|these|them))\b', user_msg, re.I))
            or (qu_raw.category and (qu_raw.brand or qu_raw.specifications or qu_raw.price.get('max') or qu_raw.use_case))
        )
        if is_standalone:
            self.context.clear()
            self._apply_qu_to_context(qu_raw, user_msg)
            normalized_q = qu_raw.normalized_query if qu_raw.normalized_query else user_msg
            return self.context, qu_raw, normalized_q

        # ── Follow-up Modifications on existing shopping context ───────────────
        # ── 2. Check for explicit Constraint Removals ("forget i5", "without graphics") ─
        removals = self._detect_removals(user_msg)
        if removals:
            for rem in removals:
                self._remove_constraint(rem)
            print(f"[ConversationManager] Removed constraints: {removals}")

        # ── 3. Check for Budget Modifications ("make it 60k", "under 60k") ─────
        new_budget = self._detect_budget_mod(user_msg)
        if new_budget is not None:
            old_b_str = f"₹{self.context.max_price:,}" if self.context.max_price is not None else "None"
            new_b_str = f"₹{new_budget:,}"
            print(f"[ConversationManager] Budget updated: {old_b_str} -> {new_b_str}")
            self.context.max_price = new_budget

        # ── 4. Check for Brand Switches ("show me dell instead", "what about lenovo") ──
        if qu_raw.brands:
            if len(qu_raw.brands) == 1:
                print(f"[ConversationManager] Brand updated: '{self.context.brand}' -> '{qu_raw.brands[0]}'")
                self.context.brand = qu_raw.brands[0]
                self.context.brands = list(qu_raw.brands)
            else:
                self.context.brands = list(qu_raw.brands)
                self.context.brand = None

        # ── 5. Check for Color Updates ("black colour", "only in blue") ───────
        if qu_raw.color:
            print(f"[ConversationManager] Color updated: '{self.context.color}' -> '{qu_raw.color}'")
            self.context.color = qu_raw.color

        # ── 6. Check for Specs Additions ("only 16GB", "with dedicated graphics") ─
        if qu_raw.specifications:
            for k, v in qu_raw.specifications.items():
                if k not in removals:
                    print(f"[ConversationManager] Spec updated: {k} -> {v}")
                    self.context.specifications[k] = v

        # ── 7. Check for Use-Case ("for gaming", "for coding") ────────────────
        if qu_raw.use_case:
            self.context.use_case = qu_raw.use_case

        # Re-derive hard requirements and soft preferences for context
        self._rebuild_context_requirements()

        # ── Synthesize Effective Query WITHOUT Destroying User Intent ─────────
        # For comparison follow-ups:
        if (self.context.last_intent == 'comparison'
                and self.context.last_comparison_items
                and not qu_raw.category
                and not qu_raw.brands
                and new_budget is None
                and not removals):
            cmp_prefix = " vs ".join(self.context.last_comparison_items)
            effective_query_str = f"{cmp_prefix} {user_msg}"
            effective_qu = qu_raw
            effective_qu.intent = 'comparison'
            effective_qu.search_required = False
            print(f"[ConversationManager] Comparison follow-up synthesized: {effective_query_str!r}")
            return self.context, effective_qu, effective_query_str

        # For product refinement follow-ups (e.g. "under 60k", "with 16GB RAM"):
        # We enrich qu_raw with active context slots while preserving the user's intent.
        effective_qu = copy.deepcopy(qu_raw)

        if not effective_qu.category and self.context.category:
            effective_qu.category = self.context.category
        if not effective_qu.audio_type and self.context.audio_type:
            effective_qu.audio_type = self.context.audio_type
        if not effective_qu.brand and self.context.brand:
            effective_qu.brand = self.context.brand
            effective_qu.brands = [self.context.brand]
        elif not effective_qu.brands and self.context.brands:
            effective_qu.brands = list(self.context.brands)
        if not effective_qu.color and self.context.color:
            effective_qu.color = self.context.color
        if effective_qu.price.get('max') is None and self.context.max_price is not None:
            effective_qu.price['max'] = self.context.max_price
        if effective_qu.price.get('min') is None and self.context.min_price is not None:
            effective_qu.price['min'] = self.context.min_price

        # Sync specifications with active context specifications
        effective_qu.specifications = copy.deepcopy(self.context.specifications)

        # Keep hard requirements in sync
        effective_qu.hard_requirements = list(self.context.hard_requirements)
        effective_qu.soft_preferences = list(self.context.soft_preferences)

        # Build clean effective query string for search API
        # Rule: Context adds information, but never reduces user query to only brand/category
        effective_query_str = self.context.synthesize_effective_query()

        self.context.last_query_raw = user_msg
        self.context.turn_count += 1

        return self.context, effective_qu, effective_query_str

    def _apply_qu_to_context(self, qu: QueryUnderstanding, raw_msg: str):
        """Populates context from a fresh QueryUnderstanding object."""
        self.context.category       = qu.category
        self.context.audio_type     = qu.audio_type
        self.context.brand          = qu.brand if isinstance(qu.brand, str) else None
        self.context.brands         = list(qu.brands)
        self.context.min_price      = qu.price.get('min')
        self.context.max_price      = qu.price.get('max')
        self.context.specifications = copy.deepcopy(qu.specifications)
        self.context.color          = qu.color
        self.context.use_case       = qu.use_case
        self.context.hard_requirements = list(qu.hard_requirements)
        self.context.soft_preferences  = list(qu.soft_preferences)
        self.context.last_query_raw = raw_msg
        self.context.turn_count = 1

    def _detect_budget_mod(self, text: str) -> int | None:
        """Parses price modifications like 'make it 60k', 'under 60000', 'budget 60k'."""
        m = self._PRICE_MOD_RE.search(text)
        if m:
            val_str = m.group(1).lower().replace(',', '')
            if 'k' in val_str:
                num = float(val_str.replace('k', '')) * 1000
                return int(num)
            try:
                return int(val_str)
            except ValueError:
                pass
        return None

    def _detect_removals(self, text: str) -> list[str]:
        """Detects requests to remove/forget constraints (e.g. 'forget i5', 'no graphics')."""
        matches = self._REMOVAL_RE.findall(text)
        removals = []
        for term in matches:
            t = term.lower()
            if t in ('i3', 'i5', 'i7', 'i9', 'ryzen', 'cpu', 'processor'):
                removals.append('cpu')
            elif t in ('ram', '16gb', '8gb'):
                removals.append('ram')
            elif t in ('graphics', 'gpu', 'dedicated gpu'):
                removals.append('gpu')
            elif t == 'anc':
                removals.append('anc')
            elif t in ('brand',):
                removals.append('brand')
            elif t in ('color', 'colour'):
                removals.append('color')
            elif t in ('budget', 'price'):
                removals.append('price')
        return list(set(removals))

    def _remove_constraint(self, constraint_key: str):
        """Removes a specific constraint from the active shopping context."""
        if constraint_key in ('cpu', 'ram', 'gpu', 'anc', 'storage'):
            self.context.specifications.pop(constraint_key, None)
        elif constraint_key == 'brand':
            self.context.brand = None
            self.context.brands = []
        elif constraint_key == 'color':
            self.context.color = None
        elif constraint_key == 'price':
            self.context.max_price = None
            self.context.min_price = None

    def _rebuild_context_requirements(self):
        """Reconstructs hard_requirements and soft_preferences lists from active state."""
        hard = []
        soft = []

        if self.context.category:
            hard.append(f"category: {self.context.category}")
        if self.context.brands:
            for b in self.context.brands:
                hard.append(f"brand: {b}")
        elif self.context.brand:
            hard.append(f"brand: {self.context.brand}")
        if self.context.color:
            hard.append(f"color: {self.context.color}")
        if self.context.max_price is not None:
            hard.append(f"price <= {self.context.max_price}")
        if self.context.min_price is not None:
            hard.append(f"price >= {self.context.min_price}")

        for k, v in self.context.specifications.items():
            hard.append(f"{k}: {v}")

        if self.context.use_case:
            soft.append(f"use_case: {self.context.use_case}")

        self.context.hard_requirements = hard
        self.context.soft_preferences  = soft
