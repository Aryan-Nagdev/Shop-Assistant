"""
material_analyzer.py  –  Product Component & Material Intelligence
──────────────────────────────────────────────────────────────────
Identifies a product's key parts/components and the real-world
materials used for each, using Groq LLM with a robust static
fallback registry for common product categories.

Flow:
  product info (title, brand, category)
        ↓
  LLM Groq call (openai/gpt-oss-20b, structured JSON)
        ↓  (on failure / timeout → fallback)
  Static Category Registry
        ↓
  [{ part, material, icon, confidence, description }, ...]
"""
from __future__ import annotations
import os, sys, re, json, hashlib
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── In-process cache (title hash → materials list) ───────────────────────────
_CACHE: dict[str, list[dict]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. STATIC FALLBACK MATERIAL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

_FALLBACK_REGISTRY: dict[str, list[dict]] = {

    # ── Computing ──────────────────────────────────────────────────────────────
    "laptop": [
        {"part": "Chassis / Body",  "material": "Aluminum Alloy / Magnesium Alloy", "icon": "🏗️", "confidence": "high",   "description": "Lightweight metal alloy for structural rigidity and heat dissipation"},
        {"part": "Display Panel",   "material": "IPS LCD / OLED Glass",            "icon": "🖥️", "confidence": "high",   "description": "Tempered glass panel with anti-glare coating for sharp visuals"},
        {"part": "Battery",         "material": "Lithium-Ion (Li-Ion)",             "icon": "🔋", "confidence": "high",   "description": "High energy-density rechargeable battery cell"},
        {"part": "Keyboard Keys",   "material": "ABS Plastic",                      "icon": "⌨️", "confidence": "high",   "description": "Acrylonitrile Butadiene Styrene — durable, impact-resistant thermoplastic"},
        {"part": "Cooling Fan",     "material": "Copper Heat Pipes + Aluminum Fins","icon": "🌀", "confidence": "medium", "description": "Copper conducts heat away; aluminum fins radiate it to airflow"},
        {"part": "PCB / Motherboard","material": "FR4 Fiberglass + Copper Traces",  "icon": "🔧", "confidence": "high",   "description": "Flame-retardant epoxy fiberglass substrate with copper circuit traces"},
    ],
    "desktop": [
        {"part": "Chassis",         "material": "Steel / Aluminum",                 "icon": "🏗️", "confidence": "high",   "description": "Stamped steel or extruded aluminum for structural integrity"},
        {"part": "Motherboard",     "material": "FR4 Fiberglass + Copper Traces",   "icon": "🔧", "confidence": "high",   "description": "Flame-retardant epoxy fiberglass with copper circuitry"},
        {"part": "CPU Cooler",      "material": "Copper Base + Aluminum Fins",       "icon": "🌀", "confidence": "high",   "description": "Copper draws heat; aluminum fins + fan dissipate it"},
        {"part": "Storage (SSD)",   "material": "NAND Flash (Silicon)",              "icon": "💾", "confidence": "high",   "description": "NAND flash memory cells built on silicon wafers"},
        {"part": "Power Supply",    "material": "Aluminum Casing + Copper Winding",  "icon": "⚡", "confidence": "medium", "description": "Aluminum shell with copper transformer winding for power conversion"},
    ],

    # ── Smartphones ────────────────────────────────────────────────────────────
    "phone": [
        {"part": "Frame / Rail",    "material": "Aluminum 6000-series",             "icon": "📱", "confidence": "high",   "description": "Aircraft-grade aluminum alloy balancing weight and durability"},
        {"part": "Display",         "material": "Corning Gorilla Glass / AMOLED",   "icon": "🖥️", "confidence": "high",   "description": "Chemically strengthened glass over OLED/LCD display panel"},
        {"part": "Back Panel",      "material": "Polycarbonate / Gorilla Glass",    "icon": "🔵", "confidence": "medium", "description": "Plastic or glass back depending on tier; glass enables wireless charging"},
        {"part": "Battery",         "material": "Lithium-Ion / Lithium-Polymer",    "icon": "🔋", "confidence": "high",   "description": "Li-Po cells common in thin phones; higher energy density than Li-Ion"},
        {"part": "Camera Lens",     "material": "Sapphire Glass / Optical Plastic", "icon": "📷", "confidence": "medium", "description": "Sapphire-coated or multi-element optical glass for scratch resistance"},
        {"part": "Charging Port",   "material": "Stainless Steel + Copper Pins",    "icon": "🔌", "confidence": "high",   "description": "Steel shell for mechanical durability; copper contacts for conductivity"},
    ],
    "smartphone": [
        {"part": "Frame / Rail",    "material": "Aluminum 6000-series",             "icon": "📱", "confidence": "high",   "description": "Aircraft-grade aluminum alloy balancing weight and durability"},
        {"part": "Display",         "material": "Corning Gorilla Glass / AMOLED",   "icon": "🖥️", "confidence": "high",   "description": "Chemically strengthened glass over OLED/LCD display panel"},
        {"part": "Back Panel",      "material": "Polycarbonate / Gorilla Glass",    "icon": "🔵", "confidence": "medium", "description": "Plastic or glass back depending on tier; glass enables wireless charging"},
        {"part": "Battery",         "material": "Lithium-Ion / Lithium-Polymer",    "icon": "🔋", "confidence": "high",   "description": "Li-Po cells common in thin phones; higher energy density than Li-Ion"},
        {"part": "Camera Lens",     "material": "Sapphire Glass / Optical Plastic", "icon": "📷", "confidence": "medium", "description": "Sapphire-coated or multi-element optical glass for scratch resistance"},
        {"part": "Charging Port",   "material": "Stainless Steel + Copper Pins",    "icon": "🔌", "confidence": "high",   "description": "Steel shell for mechanical durability; copper contacts for conductivity"},
    ],

    # ── Audio ──────────────────────────────────────────────────────────────────
    "earbuds": [
        {"part": "Outer Shell",     "material": "ABS Plastic",                      "icon": "🎧", "confidence": "high",   "description": "Lightweight thermoplastic for the earbud housing — impact resistant"},
        {"part": "Driver Unit",     "material": "Neodymium Magnet + Mylar Diaphragm","icon": "🔊", "confidence": "high",   "description": "Neodymium magnets generate the magnetic field; Mylar/PEN diaphragm vibrates to produce sound"},
        {"part": "Ear Tip",         "material": "Medical-Grade Silicone",            "icon": "👂", "confidence": "high",   "description": "Soft, hypoallergenic silicone for comfort and passive noise isolation"},
        {"part": "Charging Case",   "material": "Polycarbonate (PC) Plastic",        "icon": "🔋", "confidence": "high",   "description": "Hard-wearing PC shell that protects buds and houses the charging battery"},
        {"part": "Internal Battery","material": "Lithium-Polymer (Li-Po)",           "icon": "⚡", "confidence": "high",   "description": "Ultra-thin Li-Po cells fit the compact form factor of earbuds"},
        {"part": "Stem / Nozzle",   "material": "Polycarbonate + Mesh Filter",       "icon": "🎙️", "confidence": "medium", "description": "Plastic nozzle with acoustic mesh to protect the driver from debris"},
    ],
    "earphones": [
        {"part": "Housing",         "material": "ABS Plastic / Aluminum",            "icon": "🎧", "confidence": "high",   "description": "Plastic or metal housing; aluminum versions offer better resonance control"},
        {"part": "Driver",          "material": "Neodymium Magnet + Mylar Diaphragm","icon": "🔊", "confidence": "high",   "description": "Magnetic motor assembly that converts electrical signal to sound"},
        {"part": "Cable",           "material": "TPE (Thermoplastic Elastomer)",     "icon": "🔗", "confidence": "high",   "description": "Flexible, rubber-like plastic that resists tangling and breakage"},
        {"part": "Ear Tip",         "material": "Silicone",                          "icon": "👂", "confidence": "high",   "description": "Soft silicone creates a seal for passive isolation and bass response"},
        {"part": "Connector",       "material": "Gold-Plated Copper",                "icon": "🔌", "confidence": "high",   "description": "Gold plating prevents oxidation for consistent electrical signal"},
    ],
    "headphones": [
        {"part": "Headband",        "material": "Steel + Memory Foam + PU Leather", "icon": "🏗️", "confidence": "high",   "description": "Steel spring provides clamping force; foam + leather for headband comfort"},
        {"part": "Ear Cup Pad",     "material": "Memory Foam + PU / Velour Fabric", "icon": "🎧", "confidence": "high",   "description": "Viscoelastic foam conforms to ear shape; PU leather or velour for the cover"},
        {"part": "Driver",          "material": "Neodymium Magnet + PET Diaphragm", "icon": "🔊", "confidence": "high",   "description": "Large 40–50mm drivers for rich audio; PET (Polyethylene Terephthalate) diaphragm"},
        {"part": "Housing",         "material": "ABS Plastic / Aluminum",           "icon": "💿", "confidence": "high",   "description": "Outer shell in ABS or metal; some premium models use carbon fiber"},
        {"part": "Internal Battery","material": "Lithium-Ion",                      "icon": "🔋", "confidence": "high",   "description": "Rechargeable Li-Ion cell for wireless models — up to 30–40 hour playtime"},
    ],
    "speaker": [
        {"part": "Woofer Cone",     "material": "Polypropylene / Paper + Rubber",   "icon": "🔊", "confidence": "high",   "description": "Polypropylene cone is moisture resistant; rubber surround absorbs resonance"},
        {"part": "Cabinet / Shell", "material": "ABS Plastic / Fabric Mesh",        "icon": "🏗️", "confidence": "high",   "description": "ABS plastic body with fabric grille for acoustic transparency"},
        {"part": "Magnet",          "material": "Ferrite / Neodymium Magnet",       "icon": "🧲", "confidence": "high",   "description": "Ferrite is cost-effective; neodymium is compact and powerful"},
        {"part": "Battery",         "material": "Lithium-Ion",                      "icon": "🔋", "confidence": "high",   "description": "Large-capacity Li-Ion cells for hours of wireless playback"},
        {"part": "Passive Radiator","material": "PET Film Diaphragm",               "icon": "🎵", "confidence": "medium", "description": "Unpowered membrane that resonates to boost bass output"},
    ],

    # ── Footwear ───────────────────────────────────────────────────────────────
    "shoes": [
        {"part": "Upper",           "material": "Engineered Mesh / Knit Fabric",    "icon": "👟", "confidence": "high",   "description": "Breathable woven mesh allows airflow; stretch knit provides sock-like fit"},
        {"part": "Midsole",         "material": "EVA Foam / Phylon",                "icon": "🛡️", "confidence": "high",   "description": "Ethylene Vinyl Acetate foam provides cushioning and energy return"},
        {"part": "Outsole",         "material": "Carbon Rubber / Blown Rubber",     "icon": "🔲", "confidence": "high",   "description": "Carbon rubber in high-wear zones; blown rubber (lighter) in heel for cushion"},
        {"part": "Insole / Sockliner","material": "Memory Foam / OrthoLite",        "icon": "🦶", "confidence": "high",   "description": "Removable foam insole that conforms to foot shape and wicks moisture"},
        {"part": "Heel Counter",    "material": "Thermoplastic (TPU)",              "icon": "🔧", "confidence": "medium", "description": "Stiff TPU cup that controls heel motion and prevents overpronation"},
        {"part": "Lace & Eyelets",  "material": "Polyester + Nickel/Plastic",       "icon": "🔗", "confidence": "medium", "description": "Woven polyester laces; nickel or plastic eyelets reinforce the lace holes"},
    ],
    "sneakers": [
        {"part": "Upper",           "material": "Leather / Synthetic Leather",      "icon": "👟", "confidence": "high",   "description": "Full-grain or synthetic leather gives a classic clean aesthetic"},
        {"part": "Midsole",         "material": "EVA Foam / Air Unit",              "icon": "🛡️", "confidence": "high",   "description": "Foam midsole with possible encapsulated air unit for extra cushioning"},
        {"part": "Outsole",         "material": "Vulcanized Rubber",                "icon": "🔲", "confidence": "high",   "description": "Vulcanized (heat-treated) rubber provides grip, durability and flex"},
        {"part": "Insole",          "material": "Foam / OrthoLite",                 "icon": "🦶", "confidence": "medium", "description": "Cushioned foam footbed for all-day comfort"},
    ],

    # ── Apparel ────────────────────────────────────────────────────────────────
    "t-shirt": [
        {"part": "Main Fabric",     "material": "100% Cotton / Cotton-Polyester",   "icon": "👕", "confidence": "high",   "description": "Natural cotton is breathable & soft; polyester blend improves shape retention"},
        {"part": "Collar / Neck Rib","material": "Cotton Rib Knit",                 "icon": "🔘", "confidence": "high",   "description": "Ribbed knit retains elasticity and maintains collar shape after washing"},
        {"part": "Stitching Thread","material": "Polyester Thread",                  "icon": "🧵", "confidence": "high",   "description": "Stronger than cotton thread; resists shrinkage and breakage over washes"},
        {"part": "Dye / Print",     "material": "Reactive Dyes / Plastisol Ink",    "icon": "🎨", "confidence": "medium", "description": "Reactive dyes bond chemically to cotton fibers; plastisol ink sits on the surface for prints"},
    ],
    "shirt": [
        {"part": "Main Fabric",     "material": "Cotton / Linen / Polyester Blend", "icon": "👔", "confidence": "high",   "description": "Cotton for breathability; linen for summer; polyester blend for wrinkle resistance"},
        {"part": "Buttons",         "material": "Polyester Resin / Mother of Pearl","icon": "⚪", "confidence": "high",   "description": "Resin buttons are durable and cost-effective; MoP is used in premium shirts"},
        {"part": "Collar Interlining","material": "Non-Woven Fusible Interlining",  "icon": "🔧", "confidence": "medium", "description": "Fused backing gives structure to the collar, keeping it crisp"},
        {"part": "Stitching",       "material": "Polyester Thread",                  "icon": "🧵", "confidence": "high",   "description": "High-tensile polyester thread for seam strength and wash durability"},
    ],
    "jeans": [
        {"part": "Denim Fabric",    "material": "Cotton Denim (98% Cotton 2% Elastane)","icon": "👖", "confidence": "high", "description": "Twill-woven cotton with small elastane content for stretch comfort"},
        {"part": "Rivets",          "material": "Copper / Brass",                   "icon": "🔩", "confidence": "high",   "description": "Metal rivets reinforce stress points like pockets — traditionally copper"},
        {"part": "Zipper",          "material": "Nylon Coil / Metal Teeth",         "icon": "🔗", "confidence": "high",   "description": "Nylon zippers are lightweight; metal teeth are stronger and premium"},
        {"part": "Buttons",         "material": "Metal (Zinc Alloy / Brass)",       "icon": "⚪", "confidence": "high",   "description": "Shank buttons in zinc alloy or brass for a durable waistband closure"},
        {"part": "Belt Loops",      "material": "Cotton Twill Tape",                "icon": "🧵", "confidence": "medium", "description": "Reinforced cotton strip stitched to waistband for belt threading"},
    ],
    "dress": [
        {"part": "Main Fabric",     "material": "Polyester / Rayon / Chiffon",      "icon": "👗", "confidence": "high",   "description": "Polyester resists wrinkles; rayon drapes beautifully; chiffon is sheer & elegant"},
        {"part": "Lining",          "material": "Acetate / Polyester Satin",        "icon": "🔘", "confidence": "medium", "description": "Smooth lining prevents static cling and improves drape"},
        {"part": "Zipper",          "material": "Nylon / Invisible Zipper",         "icon": "🔗", "confidence": "high",   "description": "Invisible zipper is concealed within the seam for clean aesthetics"},
        {"part": "Embellishments",  "material": "Sequins / Beads (Plastic/Glass)",  "icon": "✨", "confidence": "medium", "description": "Decorative elements stitched or glued onto fabric"},
    ],
    "jacket": [
        {"part": "Outer Shell",     "material": "100% Polyester / Nylon Ripstop",    "icon": "🧥", "confidence": "high",   "description": "Windproof and water-resistant synthetic shell fabric"},
        {"part": "Insulation",       "material": "Polyfill Fiber / Fleece Lining",    "icon": "❄️", "confidence": "high",   "description": "Thermal batting or fleece traps warm air for cold-weather insulation"},
        {"part": "Inner Lining",     "material": "Polyester Taffeta / Satin",         "icon": "🧵", "confidence": "high",   "description": "Smooth fabric lining reduces friction and glides over inner clothing"},
        {"part": "Zipper & Hardware","material": "YKK Metal / Molded Resin Teeth",    "icon": "🔗", "confidence": "high",   "description": "Heavy-duty closure hardware designed to withstand winter wear and strain"},
        {"part": "Cuffs & Hem",      "material": "Ribbed Knit Elastane / Elastic",   "icon": "🔘", "confidence": "medium", "description": "Elasticated ribbing seals out wind and draft at wrists and waist"},
    ],
    "office wear": [
        {"part": "Main Fabric",     "material": "100% Cotton / Cotton-Polyester Blend", "icon": "👔", "confidence": "high", "description": "Breathable formal shirting fabric with crisp finish and wrinkle resistance"},
        {"part": "Buttons",         "material": "Polyester Resin / Mother of Pearl",   "icon": "⚪", "confidence": "high", "description": "Durable resin buttons for formal shirt/trouser fastening"},
        {"part": "Interlining",     "material": "Fusible Cotton Interlining",          "icon": "🔧", "confidence": "high", "description": "Gives structure and sharpness to formal shirt collar and cuffs"},
        {"part": "Seams & Stitches","material": "High-Tensile Polyester Thread",       "icon": "🧵", "confidence": "high", "description": "Reinforced stitching maintains seam integrity over frequent washes"},
    ],
    "trouser": [
        {"part": "Main Fabric",     "material": "100% Cotton / Cotton Twill / Chino",  "icon": "👖", "confidence": "high", "description": "Durable twill weave offering comfort, breathability, and structure"},
        {"part": "Rivets & Fasteners","material": "Copper / Brass / Zinc Alloy",       "icon": "🔩", "confidence": "high", "description": "Metal rivets reinforce pocket stress points; metal shank or button waistband"},
        {"part": "Zipper Fly",      "material": "Brass / Metal Teeth (YKK)",           "icon": "🔗", "confidence": "high", "description": "Sturdy metal zipper designed for daily pants closure"},
        {"part": "Pocket Lining",   "material": "Cotton Sheeting / Poplin",            "icon": "🔲", "confidence": "high", "description": "Lightweight cotton lining for interior pocket bags"},
        {"part": "Waistband",       "material": "Interlined Cotton Twill",             "icon": "🧵", "confidence": "high", "description": "Fusible interlining inside waistband prevents stretching"},
    ],

    # ── Kitchen / Appliances ───────────────────────────────────────────────────
    "pressure cooker": [
        {"part": "Body / Pot",      "material": "Stainless Steel (304) / Aluminum", "icon": "🍳", "confidence": "high",   "description": "Food-grade SS304 for corrosion resistance; aluminum for faster heat distribution"},
        {"part": "Lid",             "material": "Stainless Steel / Aluminum",       "icon": "🔲", "confidence": "high",   "description": "Matched metal lid with locking lugs to create pressure seal"},
        {"part": "Gasket / Seal",   "material": "Food-Grade Silicone / EPDM Rubber","icon": "⭕", "confidence": "high",   "description": "Pressure-sealing ring — silicone lasts longer and is odor-neutral vs rubber"},
        {"part": "Handles",         "material": "Bakelite / Phenolic Resin",        "icon": "🤚", "confidence": "high",   "description": "Thermosetting plastic that resists heat — stays cool on the stovetop"},
        {"part": "Safety Valve",    "material": "Stainless Steel + Neoprene",       "icon": "⚙️", "confidence": "high",   "description": "SS valve body with neoprene seal — releases excess steam to prevent over-pressure"},
        {"part": "Base / Triply",   "material": "Capsule Bottom (SS + Aluminum)",   "icon": "🔲", "confidence": "medium", "description": "Sandwich base spreads heat evenly — stainless outer, aluminum core, stainless inner"},
    ],
    "cookware": [
        {"part": "Body",            "material": "Stainless Steel / Aluminum / Cast Iron","icon": "🍳", "confidence": "high", "description": "SS for durability; aluminum for conductivity; cast iron for heat retention"},
        {"part": "Non-Stick Coating","material": "PTFE (Teflon) / Ceramic Coating", "icon": "⭕", "confidence": "high",   "description": "PTFE is classic non-stick; ceramic is PFOA-free and scratch-resistant"},
        {"part": "Handle",          "material": "Stainless Steel / Bakelite",       "icon": "🤚", "confidence": "high",   "description": "SS stays cool on induction; Bakelite stays cool on gas — both heat-insulating"},
        {"part": "Lid",             "material": "Tempered Glass / Stainless Steel", "icon": "🔲", "confidence": "high",   "description": "Tempered glass lets you monitor food; SS is more durable and dishwasher-safe"},
    ],

    # ── Cameras ────────────────────────────────────────────────────────────────
    "camera": [
        {"part": "Body",            "material": "Magnesium Alloy / Polycarbonate",  "icon": "📷", "confidence": "high",   "description": "Magnesium alloy in professional/semi-pro bodies for weather sealing and rigidity"},
        {"part": "Lens Elements",   "material": "Optical Glass / ED Glass",         "icon": "🔍", "confidence": "high",   "description": "Multi-coated optical glass elements; ED (Extra-low Dispersion) minimizes chromatic aberration"},
        {"part": "Sensor",          "material": "Silicon (CMOS Wafer)",             "icon": "💡", "confidence": "high",   "description": "CMOS image sensor on a silicon substrate captures light for digital imaging"},
        {"part": "Shutter",         "material": "Carbon Fiber / Aluminum Blades",   "icon": "⚙️", "confidence": "medium", "description": "Ultra-thin blades on a focal plane shutter; carbon fiber in high-speed shutters"},
        {"part": "Battery",         "material": "Lithium-Ion",                      "icon": "🔋", "confidence": "high",   "description": "LP-E style Li-Ion battery packs — optimized for low-temperature performance"},
        {"part": "Grip",            "material": "Rubber (EPDM) + ABS Plastic",      "icon": "🤚", "confidence": "high",   "description": "Textured rubber grip coating over plastic body for secure handling"},
    ],

    # ── Smartwatch ─────────────────────────────────────────────────────────────
    "smartwatch": [
        {"part": "Case",            "material": "Aluminum / Stainless Steel / Titanium","icon": "⌚", "confidence": "high", "description": "Aluminum for lightweight; SS for scratch resistance; titanium for premium durability"},
        {"part": "Display Glass",   "material": "Ion-X Glass / Sapphire Crystal",   "icon": "🖥️", "confidence": "high",   "description": "Ion-X (toughened glass) on standard; sapphire crystal on premium models — virtually scratchproof"},
        {"part": "Band / Strap",    "material": "Fluoroelastomer / Silicone",       "icon": "🔗", "confidence": "high",   "description": "Fluoroelastomer (Apple FKM) is sweat & UV resistant; silicone is softer and cheaper"},
        {"part": "Battery",         "material": "Lithium-Ion",                      "icon": "🔋", "confidence": "high",   "description": "Compact custom Li-Ion cell shaped to fit the case"},
        {"part": "Optical Sensor",  "material": "LED + Photodiode (Silicon)",       "icon": "❤️", "confidence": "high",   "description": "Green LEDs + photodiodes detect blood flow for heart rate and SpO2 measurement"},
    ],

    # ── Bags / Accessories ─────────────────────────────────────────────────────
    "bag": [
        {"part": "Outer Shell",     "material": "Nylon / Polyester / Canvas",       "icon": "🎒", "confidence": "high",   "description": "Nylon is lightweight and water resistant; canvas is durable and aesthetic"},
        {"part": "Zippers",         "material": "Nylon Coil / Metal (YKK Brass)",   "icon": "🔗", "confidence": "high",   "description": "YKK zippers are the industry standard — metal teeth for heavy-duty bags"},
        {"part": "Lining",          "material": "Polyester Fabric",                  "icon": "🔘", "confidence": "medium", "description": "Interior lining protects contents and adds structure to the bag"},
        {"part": "Straps",          "material": "Nylon Webbing + Foam Padding",     "icon": "🎽", "confidence": "high",   "description": "Nylon webbing carries load; foam padding reduces shoulder strain"},
        {"part": "Frame / Structure","material": "Polypropylene / Aluminum Stays",  "icon": "🏗️", "confidence": "medium", "description": "Rigid PP sheet or aluminum stays maintain bag shape when loaded"},
    ],
    "backpack": [
        {"part": "Outer Shell",     "material": "600D Polyester / Nylon",           "icon": "🎒", "confidence": "high",   "description": "600D (denier) polyester is the most common backpack fabric — tough and water resistant"},
        {"part": "Zippers",         "material": "Nylon Coil / Metal (YKK)",         "icon": "🔗", "confidence": "high",   "description": "YKK nylon coil is smooth and durable — the standard in backpacks"},
        {"part": "Shoulder Straps", "material": "EVA Foam + Mesh + Polyester",      "icon": "🎽", "confidence": "high",   "description": "EVA foam cushioning with mesh for airflow — keeps shoulders comfortable and dry"},
        {"part": "Back Panel",      "material": "EVA Foam + Air Mesh",              "icon": "🔲", "confidence": "high",   "description": "Contoured foam back with ventilated mesh reduces heat buildup against the back"},
    ],
}

# Alias mapping to canonicalize category names
_CATEGORY_ALIASES: dict[str, str] = {
    "mobile": "smartphone",
    "mobile phone": "smartphone",
    "cell phone": "smartphone",
    "iphone": "smartphone",
    "android": "smartphone",
    "notebook": "laptop",
    "ultrabook": "laptop",
    "chromebook": "laptop",
    "tws": "earbuds",
    "wireless earbuds": "earbuds",
    "in-ear": "earphones",
    "over-ear": "headphones",
    "on-ear": "headphones",
    "wireless headphones": "headphones",
    "running shoes": "shoes",
    "sports shoes": "shoes",
    "walking shoes": "shoes",
    "casual shoes": "sneakers",
    "lifestyle shoes": "sneakers",
    "tshirt": "t-shirt",
    "top": "t-shirt",
    "formal shirt": "shirt",
    "casual shirt": "shirt",
    "cooker": "pressure cooker",
    "dslr": "camera",
    "mirrorless": "camera",
    "watch": "smartwatch",
    "fitness band": "smartwatch",
    "fitness tracker": "smartwatch",
    "purse": "bag",
    "handbag": "bag",
    "laptop bag": "backpack",
    "school bag": "backpack",
    "winter jacket": "jacket",
    "winter wear": "jacket",
    "coat": "jacket",
    "blazer": "office wear",
    "formal wear": "office wear",
    "work wear": "office wear",
    "office shirt": "shirt",
    "formal shirt": "shirt",
    "pants": "trouser",
    "trousers": "trouser",
    "chinos": "trouser",
    "cargo pant": "trouser",
}


def _resolve_category(raw: str | None) -> str | None:
    """Normalize category to a key in the fallback registry."""
    if not raw:
        return None
    lowered = raw.strip().lower()
    # Direct match
    if lowered in _FALLBACK_REGISTRY:
        return lowered
    # Alias match
    if lowered in _CATEGORY_ALIASES:
        alias = _CATEGORY_ALIASES[lowered]
        if alias in _FALLBACK_REGISTRY:
            return alias
    # Substring match
    for key in _FALLBACK_REGISTRY:
        if key in lowered or lowered in key:
            return key
    return None


def _infer_category_from_title(title: str) -> str | None:
    """Guess product category from the product title when category is missing."""
    t = title.lower()
    if any(w in t for w in ["laptop", "notebook", "macbook", "chromebook"]):
        return "laptop"
    if any(w in t for w in ["phone", "iphone", "samsung galaxy", "oneplus", "redmi", "pixel", "poco"]):
        return "smartphone"
    if any(w in t for w in ["earbuds", "airdopes", "tws", "galaxy buds", "airpods"]):
        return "earbuds"
    if any(w in t for w in ["earphone", "basshead", "wired earphone"]):
        return "earphones"
    if any(w in t for w in ["headphone", "over-ear", "on-ear", "headset", "wh-"]):
        return "headphones"
    if any(w in t for w in ["speaker", "soundbar"]):
        return "speaker"
    if any(w in t for w in ["shoes", "sneakers", "running", "footwear", "boot", "slipper"]):
        return "shoes"
    if any(w in t for w in ["jacket", "coat", "blazer", "windcheater", "windbreaker", "winter wear", "sweater", "hoodie"]):
        return "jacket"
    if any(w in t for w in ["t-shirt", "tshirt", "polo", "tee"]):
        return "t-shirt"
    if any(w in t for w in ["office wear", "formal wear", "work wear"]):
        return "office wear"
    if any(w in t for w in ["shirt", "formal shirt", "cotton shirt"]):
        return "shirt"
    if any(w in t for w in ["trouser", "pants", "chinos", "cargos"]):
        return "trouser"
    if any(w in t for w in ["jeans", "denim"]):
        return "jeans"
    if any(w in t for w in ["dress", "kurti", "salwar", "saree", "kurta"]):
        return "dress"
    if any(w in t for w in ["pressure cooker", "cooker", "prestige", "hawkins"]):
        return "pressure cooker"
    if any(w in t for w in ["smartwatch", "watch", "band", "fitbit", "garmin"]):
        return "smartwatch"
    if any(w in t for w in ["camera", "dslr", "mirrorless", "eos", "nikon", "fujifilm"]):
        return "camera"
    if any(w in t for w in ["backpack", "laptop bag", "school bag", "rucksack"]):
        return "backpack"
    if any(w in t for w in ["handbag", "purse", "tote", "sling"]):
        return "bag"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LLM-POWERED MATERIAL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

_LLM_SYSTEM = """You are a material science and product engineering expert.
Given a product name, brand, and category, identify the key components/parts
and the exact real-world materials used for each.

RULES:
- Return ONLY valid JSON. No markdown. No explanation outside JSON.
- List 4 to 6 parts. Focus on the most important parts users care about.
- Use ONLY real, verifiable materials for this product type — never invent or guess materials.
- If you're unsure about a specific product's material, use the generic industry standard material for that category.
- Confidence: "high" = definitely this material, "medium" = typical for this category, "low" = uncertain
- Icons should be relevant emojis for that part.
- Description: one concise sentence explaining the material's benefit/property.

OUTPUT FORMAT (JSON array, no wrapping object):
{
  "materials": [
    {
      "part": "<component name>",
      "material": "<exact material name>",
      "icon": "<emoji>",
      "confidence": "high" | "medium" | "low",
      "description": "<one sentence about why this material is used>"
    }
  ]
}"""


def _call_llm(title: str, brand: str | None, category: str | None) -> list[dict] | None:
    """Call Groq LLM to get material breakdown. Returns None on failure."""
    try:
        import os
        from groq import Groq
        import config
        key = config.get_groq_api_key()
        if not key:
            return None

        client = Groq(api_key=key)
        prompt = (
            f"Product: {title}\n"
            f"Brand: {brand or 'Unknown'}\n"
            f"Category: {category or 'General'}\n\n"
            "Identify the key components and exact materials used in this product."
        )

        for model_name in config.GROQ_MODELS:
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": _LLM_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=600,
                    timeout=5.0,
                )
                raw = resp.choices[0].message.content.strip()
                raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.DOTALL).strip()

                data = json.loads(raw, strict=False)
                materials = data.get("materials") if isinstance(data, dict) else data
                if not isinstance(materials, list) or len(materials) == 0:
                    continue

                # Validate each entry has required keys
                valid = []
                for m in materials:
                    if isinstance(m, dict) and m.get("part") and m.get("material"):
                        valid.append({
                            "part":        str(m.get("part", "")).strip(),
                            "material":    str(m.get("material", "")).strip(),
                            "icon":        str(m.get("icon", "🔧")).strip() or "🔧",
                            "confidence":  m.get("confidence", "medium") if m.get("confidence") in ("high","medium","low") else "medium",
                            "description": str(m.get("description", "")).strip(),
                        })
                if valid:
                    return valid
            except Exception as e_mod:
                continue

        return None

    except Exception as e:
        print(f"[MaterialAnalyzer] LLM call failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def get_materials(
    title: str,
    category: str | None = None,
    brand: str | None = None,
    description: str | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """
    Main entry point. Returns a list of material dicts for a product.

    Priority:
      1. In-process cache (if use_cache=True)
      2. Groq LLM analysis
      3. Static fallback registry by category
      4. Generic 'consumer product' fallback
    """
    title = (title or "").strip()
    if not title:
        return []

    # Cache key
    cache_key = hashlib.md5(title.lower().encode()).hexdigest()
    if use_cache and cache_key in _CACHE:
        print(f"[MaterialAnalyzer] Cache hit for: {title[:40]!r}")
        return _CACHE[cache_key]

    # Resolve category
    resolved_cat = _resolve_category(category) or _infer_category_from_title(title)

    # 1. Try LLM
    llm_result = _call_llm(title, brand, resolved_cat or category)
    if llm_result:
        print(f"[MaterialAnalyzer] LLM success for: {title[:40]!r} ({len(llm_result)} parts)")
        if use_cache:
            _CACHE[cache_key] = llm_result
        return llm_result

    # 2. Fallback registry
    if resolved_cat and resolved_cat in _FALLBACK_REGISTRY:
        fallback = _FALLBACK_REGISTRY[resolved_cat]
        print(f"[MaterialAnalyzer] Fallback registry for category={resolved_cat!r}: {len(fallback)} parts")
        if use_cache:
            _CACHE[cache_key] = fallback
        return fallback

    # Check if title or category suggests apparel/fashion
    is_apparel = any(w in title.lower() for w in [
        "jacket", "coat", "shirt", "pant", "trouser", "jean", "denim", "suit", "blazer",
        "cotton", "polyester", "wool", "fleece", "t-shirt", "tee", "hoodie", "sweater",
        "dress", "kurta", "kurti", "wear", "fabric", "cloth", "chinos"
    ]) or (resolved_cat in ["jacket", "shirt", "trouser", "jeans", "t-shirt", "dress", "office wear", "apparel"])

    if is_apparel:
        generic_apparel = [
            {"part": "Main Fabric", "material": "100% Cotton / Polyester Blend", "icon": "🧵", "confidence": "high", "description": "Durable, breathable textile blend for everyday wear"},
            {"part": "Buttons / Zipper", "material": "Resin / Metal Alloy", "icon": "🔘", "confidence": "high", "description": "Sturdy fastening components designed for longevity"},
            {"part": "Stitching", "material": "Reinforced Polyester Thread", "icon": "🪡", "confidence": "medium", "description": "High-tensile seam stitching to prevent tearing"},
        ]
        if use_cache:
            _CACHE[cache_key] = generic_apparel
        return generic_apparel

    # 3. Generic consumer product fallback
    generic = [
        {"part": "Main Body",       "material": "ABS Plastic / Aluminum",   "icon": "🏗️", "confidence": "low", "description": "Common construction materials for consumer electronics"},
        {"part": "Internal Battery","material": "Lithium-Ion",               "icon": "🔋", "confidence": "medium", "description": "Standard rechargeable battery used in most portable electronics"},
        {"part": "Connectors",      "material": "Gold-Plated Copper",        "icon": "🔌", "confidence": "medium", "description": "Gold plating prevents oxidation for reliable electrical contacts"},
    ]
    print(f"[MaterialAnalyzer] Using generic fallback for: {title[:40]!r}")
    if use_cache:
        _CACHE[cache_key] = generic
    return generic


_TITLE_MATERIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bcotton\s*blend\b', re.I), 'cotton blend'),
    (re.compile(r'\b100%\s*cotton\b|\bpure\s*cotton\b|\bcotton\b', re.I), 'cotton'),
    (re.compile(r'\bpoly\s*cotton\b|\bpolycotton\b', re.I), 'poly-cotton'),
    (re.compile(r'\bpolyester\b', re.I), 'polyester'),
    (re.compile(r'\blinen\b', re.I), 'linen'),
    (re.compile(r'\bdenim\b', re.I), 'denim'),
    (re.compile(r'\bleather\b', re.I), 'leather'),
    (re.compile(r'\bmesh\b', re.I), 'mesh'),
    (re.compile(r'\bnylon\b', re.I), 'nylon'),
    (re.compile(r'\brayon\b|\bviscose\b', re.I), 'rayon/viscose'),
    (re.compile(r'\bknit\b', re.I), 'knit fabric'),
    (re.compile(r'\beva\b|\bphylon\b', re.I), 'EVA foam'),
    (re.compile(r'\brubber\b', re.I), 'rubber'),
    (re.compile(r'\bsuede\b', re.I), 'suede'),
    (re.compile(r'\bcanvas\b', re.I), 'canvas'),
    (re.compile(r'\bwool\b', re.I), 'wool'),
    (re.compile(r'\bsilk\b', re.I), 'silk'),
]


def materials_from_title(title: str, description: str = "") -> list[dict]:
    """Extract only materials explicitly named in the listing text. Does not invent."""
    text = f"{title or ''} {description or ''}".strip()
    if not text:
        return []
    found: list[dict] = []
    seen: set[str] = set()
    for pat, name in _TITLE_MATERIAL_PATTERNS:
        if pat.search(text) and name not in seen:
            seen.add(name)
            found.append({
                "part": "Listed on product",
                "material": name,
                "icon": "🧵",
                "confidence": "high",
                "description": f"The product title/description mentions {name}.",
                "source": "title",
            })
    return found


def get_card_materials(
    title: str,
    category: str | None = None,
    brand: str | None = None,
    description: str | None = None,
) -> list[dict]:
    """
    Materials already available for a displayed product:
      1. Cache populated by /api/materials (same as the product card)
      2. Materials named in the title/description
    Does not call the LLM or use generic category guesses.
    """
    title = (title or "").strip()
    if not title:
        return []

    cache_key = hashlib.md5(title.lower().encode()).hexdigest()
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # Title/description evidence only when the card cache has not been filled.
    # Do not use the generic category registry here — that would invent materials.
    return materials_from_title(title, description or "")


def clear_cache() -> None:
    """Clear the in-process material cache."""
    global _CACHE
    _CACHE = {}
    print("[MaterialAnalyzer] Cache cleared.")
