"""
alternatives_engine.py  –  Smart Alternatives & Constraint Relaxation (Phase 3)
────────────────────────────────────────────────────────────────────────────────
When exact products are unavailable under the user's budget or constraints:
  1. Budget Relaxation: Discovers the lowest-priced product matching all requested
     specifications/brand/category and calculates the exact price difference.
  2. Specification Relaxation: Finds the best options strictly within budget
     with a clearly explained secondary spec trade-off (e.g. 8GB RAM instead of 16GB).
  3. Formulates structured alternative records with diff badges and explanations.
  4. NEVER silently changes requirements or claims an alternative is an exact match.
"""
from __future__ import annotations
import re
from typing import Any
from src.live_search import (
    NormalizedProduct,
    validate_product,
    normalize_raw_item,
    _serpapi,
    _scrapingdog,
    _rank_validated_products,
)


def find_smart_alternatives(
    query: str,
    ents: dict,
    candidate_products: list[NormalizedProduct],
    rejected_records: list[dict[str, Any]],
    top_n: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Discovers closest valid alternative products when exact search yields 0 results.
    Returns (alternative_product_dicts, alternative_metadata).
    """
    category = ents.get('category')
    audio_type = ents.get('audio_type')
    brands = ents.get('brands') or []
    max_price = ents.get('max_price')
    min_price = ents.get('min_price')
    tech_specs = ents.get('tech_specs') or {}
    colors = ents.get('colors') or []
    hard_reqs = ents.get('hard_requirements') or []
    soft_prefs = ents.get('soft_preferences') or []

    alternatives: list[dict[str, Any]] = []
    lowest_spec_match: dict[str, Any] | None = None
    in_budget_alt: dict[str, Any] | None = None

    # ══════════════════════════════════════════════════════════════════════════
    # STRATEGY 1: BUDGET RELAXATION (Find lowest price meeting ALL specs/brand)
    # ══════════════════════════════════════════════════════════════════════════
    if max_price is not None:
        # Check if any rejected candidate met all specs/category/brand but failed ONLY on price
        price_exceeded_candidates: list[NormalizedProduct] = []

        for p in candidate_products:
            # Validate without max_price constraint
            v_no_price = validate_product(
                prod=p,
                target_category=category,
                audio_type=audio_type,
                want_brands=brands,
                max_price=None,  # Relax price
                min_price=min_price,
                tech_specs=tech_specs,
                want_colors=colors,
                hard_requirements=[hr for hr in hard_reqs if not hr.startswith('price <=')],
                category_confidence=1.0,
            )
            if v_no_price.valid and p.price_num and p.price_num > max_price:
                price_exceeded_candidates.append(p)

        # If none in initial candidates (e.g. search query had 'under 30000' which filtered all 40k items),
        # fetch unconstrained candidate items for the category & specs
        if not price_exceeded_candidates:
            spec_str = ' '.join(tech_specs.values())
            brand_str = ' '.join(brands)
            cat_str = audio_type or category or 'product'
            color_str = ' '.join(colors)
            unconstrained_q = f"{brand_str} {color_str} {spec_str} {cat_str} best price India".strip()
            unconstrained_q = re.sub(r'\s+', ' ', unconstrained_q)

            raw_unconstrained = _serpapi(unconstrained_q, num=16)
            if not raw_unconstrained:
                raw_unconstrained = _scrapingdog(unconstrained_q, num=16)

            norm_unconstrained = [normalize_raw_item(it, unconstrained_q) for it in raw_unconstrained]

            for p in norm_unconstrained:
                v_no_price = validate_product(
                    prod=p,
                    target_category=category,
                    audio_type=audio_type,
                    want_brands=brands,
                    max_price=None,
                    min_price=min_price,
                    tech_specs=tech_specs,
                    want_colors=colors,
                    hard_requirements=[hr for hr in hard_reqs if not hr.startswith('price <=')],
                    category_confidence=1.0,
                )
                if v_no_price.valid and p.price_num and p.price_num > max_price:
                    price_exceeded_candidates.append(p)

        # Sort price-exceeded candidates by price ascending to find the true lowest price
        if price_exceeded_candidates:
            price_exceeded_candidates.sort(key=lambda p: p.price_num or 999999)
            best_p = price_exceeded_candidates[0]
            diff = (best_p.price_num or 0) - max_price

            d = best_p.to_dict()
            d['is_alternative'] = True
            d['alternative_type'] = 'budget_relaxed'
            d['alternative_diff'] = f"+₹{diff:,.0f} above budget"
            d['alternative_explanation'] = f"Matches your requested configuration but is ₹{diff:,.0f} above your ₹{max_price:,} budget."
            
            lowest_spec_match = d
            alternatives.append(d)

            # Add up to 2 more budget-relaxed items if available
            for extra_p in price_exceeded_candidates[1:3]:
                ed = extra_p.to_dict()
                e_diff = (extra_p.price_num or 0) - max_price
                ed['is_alternative'] = True
                ed['alternative_type'] = 'budget_relaxed'
                ed['alternative_diff'] = f"+₹{e_diff:,.0f} above budget"
                alternatives.append(ed)

    # ══════════════════════════════════════════════════════════════════════════
    # STRATEGY 2: SPECIFICATION RELAXATION (In-budget with secondary spec change)
    # ══════════════════════════════════════════════════════════════════════════
    if max_price is not None:
        in_budget_candidates: list[tuple[NormalizedProduct, str]] = []

        # 2a. Laptops: If GPU/dedicated graphics was requested under low budget (e.g. <= 30k or <= 50k),
        # look for in-budget laptops with integrated graphics or 8GB RAM
        if category == 'laptop':
            # Relax GPU requirement
            relaxed_specs_gpu = {k: v for k, v in tech_specs.items() if k != 'gpu'}
            gpu_rel_q = f"laptop Intel i5 under Rs.{max_price:,} India" if 'i5' in str(tech_specs.get('cpu')) else f"laptop under Rs.{max_price:,} India"
            raw_in_budget = _serpapi(gpu_rel_q, num=12)
            norm_in_budget = [normalize_raw_item(it, gpu_rel_q) for it in raw_in_budget]

            for p in norm_in_budget:
                v_gpu_rel = validate_product(
                    prod=p,
                    target_category=category,
                    audio_type=None,
                    want_brands=brands,
                    max_price=max_price,
                    min_price=min_price,
                    tech_specs=relaxed_specs_gpu,
                    want_colors=colors,
                    hard_requirements=[hr for hr in hard_reqs if 'gpu' not in hr.lower()],
                    category_confidence=1.0,
                )
                if v_gpu_rel.valid and p.price_num and p.price_num <= max_price:
                    diff_reason = "Integrated graphics instead of dedicated GPU" if 'gpu' in tech_specs else "In-budget alternative"
                    in_budget_candidates.append((p, diff_reason))

        # 2b. Audio: If user asked for earbuds under ₹500 (which do not exist in TWS),
        # recommend in-budget high-rated wired in-ear earphones
        elif audio_type == 'earbuds' and max_price <= 1000:
            wired_q = f"wired in-ear earphones under Rs.{max_price:,} India"
            raw_wired = _serpapi(wired_q, num=10)
            norm_wired = [normalize_raw_item(it, wired_q) for it in raw_wired]

            for p in norm_wired:
                v_wired = validate_product(
                    prod=p,
                    target_category='earphones',
                    audio_type='earphones',
                    want_brands=brands,
                    max_price=max_price,
                    min_price=min_price,
                    tech_specs={},
                    want_colors=[],
                    hard_requirements=[f"price <= {max_price}"],
                    category_confidence=1.0,
                )
                if v_wired.valid and p.price_num and p.price_num <= max_price:
                    in_budget_candidates.append((p, "Wired in-ear earphones (within ₹500 budget)"))

        if in_budget_candidates:
            # Sort by rating and price fit
            in_budget_candidates.sort(key=lambda x: (x[0].rating or 0, -(x[0].price_num or 0)), reverse=True)
            for bp, reason in in_budget_candidates[:2]:
                bd = bp.to_dict()
                bd['is_alternative'] = True
                bd['alternative_type'] = 'spec_relaxed'
                bd['alternative_diff'] = reason
                bd['alternative_explanation'] = f"Fits your budget (₹{bp.price_num:,.0f}) but features {reason}."
                if not in_budget_alt:
                    in_budget_alt = bd
                # Only add if not already in alternatives
                if not any(a.get('link') == bd.get('link') for a in alternatives):
                    alternatives.append(bd)

    # ══════════════════════════════════════════════════════════════════════════
    # COMPOSE ALTERNATIVE DIAGNOSTICS & EXPLANATION SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    meta = {
        'has_alternatives': len(alternatives) > 0,
        'lowest_spec_match': lowest_spec_match,
        'in_budget_alt': in_budget_alt,
        'total_alternatives': len(alternatives),
    }

    return alternatives[:top_n], meta
