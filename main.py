"""SaasScout API — aggregated SaaS deals, lifetime offers, and price drops."""

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DATA_FILE = Path(__file__).parent / "data" / "latest_deals.json"

app = FastAPI(
    title="SaasScout — SaaS Deals & Lifetime Deal Tracker",
    description=(
        "Real-time aggregated SaaS promotions, lifetime deals, and price drops "
        "with affiliate-tagged links. Updated daily via automated pipeline.\n\n"
        "**Deal types:** `Lifetime Deal` · `Annual Discount` · `Free Trial`\n\n"
        "**Categories:** AI · Marketing · DevTools · Productivity · Analytics · Design · Security · Finance"
    ),
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


DEAL_TYPE_MAP = {
    "ltd": "Lifetime Deal",
    "lifetime": "Lifetime Deal",
    "discount": "Annual Discount",
    "annual": "Annual Discount",
    "free_trial": "Free Trial",
    "free": "Free Trial",
    "trial": "Free Trial",
}


class Deal(BaseModel):
    id: str
    name: str
    category: str
    original_price: float
    deal_price: float
    discount_percent: float
    deal_type: str
    affiliate_url: str
    description: str
    source: str
    discovered_at: str


class PaginatedDeals(BaseModel):
    total: int
    page: int
    per_page: int
    deals: list[Deal]


def _load_deals() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _filter(
    deals: list[dict],
    *,
    category: Optional[str],
    max_price: Optional[float],
    min_discount: Optional[float],
    deal_type: Optional[str],
    q: Optional[str],
) -> list[dict]:
    if category:
        deals = [d for d in deals if d["category"].lower() == category.lower()]
    if max_price is not None:
        deals = [d for d in deals if d["deal_price"] <= max_price]
    if min_discount is not None:
        deals = [d for d in deals if d["discount_percent"] >= min_discount]
    if deal_type:
        normalised = DEAL_TYPE_MAP.get(deal_type.lower(), deal_type)
        deals = [d for d in deals if d["deal_type"].lower() == normalised.lower()]
    if q:
        lower_q = q.lower()
        deals = [
            d for d in deals
            if lower_q in d["name"].lower() or lower_q in d["description"].lower()
        ]
    return deals


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _render_homepage(deals: list[dict]) -> str:
    categories = sorted(set(d["category"] for d in deals))
    total = len(deals)

    def type_badge(t):
        if t == "Lifetime Deal":
            return '<span class="type-badge type-ltd">LTD</span>'
        if t == "Annual Discount":
            return '<span class="type-badge type-discount">DISCOUNT</span>'
        return '<span class="type-badge type-trial">FREE TRIAL</span>'

    def price_html(d):
        orig, deal, pct = d["original_price"], d["deal_price"], d["discount_percent"]
        deal_str = "Free" if deal == 0 else f"${deal:.0f}/mo"
        orig_str = f'<span class="price-original">${orig:.0f}</span>' if orig > 0 and orig != deal else ""
        pct_str = f'<span class="discount-tag">{int(pct)}% off</span>' if pct > 0 else ""
        return f'<span class="price-deal">{deal_str}</span>{orig_str}{pct_str}'

    cards = "\n".join(f"""
<article class="card" data-name="{d['name'].lower()}" data-desc="{d['description'][:80].lower()}" data-cat="{d['category']}" data-type="{d['deal_type']}">
  <div class="card-top"><div class="card-name">{d['name']}</div>{type_badge(d['deal_type'])}</div>
  <div class="card-cat">{d['category']}</div>
  <div class="card-desc">{d['description'][:120]}</div>
  <div class="card-price">{price_html(d)}</div>
  <a class="card-btn" href="{d['affiliate_url']}" target="_blank" rel="noopener">Get Deal →</a>
</article>""" for d in deals)

    cat_chips = "\n".join(f'<button class="chip" data-cat="{c}">{c}</button>' for c in categories)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SaasScout — SaaS Lifetime Deals & Price Drop Tracker</title>
<meta name="description" content="Browse {total} SaaS lifetime deals, annual discounts, and free trials across AI, Marketing, DevTools, Productivity, Analytics and more. Updated daily.">
<meta name="keywords" content="saas deals, lifetime deals, software discounts, saas lifetime deal, appsumo, software deals">
<meta property="og:title" content="SaasScout — SaaS Deals & Lifetime Deal Tracker">
<meta property="og:description" content="{total} SaaS deals tracked daily. Filter by category, deal type and discount.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://saasscout.onrender.com">
<link rel="canonical" href="https://saasscout.onrender.com">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"WebSite","name":"SaasScout","url":"https://saasscout.onrender.com","description":"SaaS lifetime deals and price drop tracker. Updated daily."}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0a14;--surface:#13131f;--border:#ffffff0f;--accent:#6366f1;--accent-dim:#6366f120;--green:#10b981;--green-dim:#10b98120;--orange:#f59e0b;--orange-dim:#f59e0b20;--blue:#3b82f6;--blue-dim:#3b82f620;--text:#f1f5f9;--muted:#94a3b8;--dim:#475569;--radius:12px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;min-height:100vh}}
nav{{border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;justify-content:space-between;height:60px;position:sticky;top:0;background:var(--bg);z-index:10}}
.logo{{font-size:20px;font-weight:800;color:var(--text);text-decoration:none}}.logo span{{color:var(--accent)}}
.nav-links{{display:flex;gap:20px;align-items:center}}.nav-links a{{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500}}
.api-btn{{background:var(--accent);color:#fff;padding:7px 16px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none}}
.hero{{text-align:center;padding:64px 24px 48px;max-width:700px;margin:0 auto}}
.badge{{display:inline-flex;align-items:center;gap:6px;background:var(--green-dim);border:1px solid var(--green);color:var(--green);padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;margin-bottom:20px}}
h1{{font-size:clamp(28px,5vw,48px);font-weight:800;line-height:1.15;margin-bottom:16px}}h1 span{{color:var(--accent)}}
.hero p{{color:var(--muted);font-size:17px;line-height:1.6;margin-bottom:32px}}
.stats{{display:flex;gap:32px;justify-content:center;flex-wrap:wrap}}
.stat-num{{font-size:28px;font-weight:800;color:var(--accent)}}.stat-label{{font-size:12px;color:var(--dim);letter-spacing:1px;margin-top:2px}}
.controls{{max-width:1100px;margin:0 auto;padding:0 24px 32px}}
.search-wrap{{position:relative;margin-bottom:20px}}
.search-icon{{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--dim)}}
#search{{width:100%;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:15px;padding:13px 16px 13px 44px;outline:none;font-family:inherit}}
#search:focus{{border-color:var(--accent)}}#search::placeholder{{color:var(--dim)}}
.filter-row{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.filter-label{{font-size:12px;color:var(--dim);font-weight:600;letter-spacing:.5px;margin-right:4px}}
.chip{{padding:6px 14px;border-radius:20px;font-size:13px;font-weight:500;border:1px solid var(--border);background:var(--surface);color:var(--muted);cursor:pointer;transition:all .15s;white-space:nowrap}}
.chip:hover,.chip.active{{border-color:var(--accent);color:var(--accent);background:var(--accent-dim)}}
.chip[data-type="Lifetime Deal"].active{{background:var(--green-dim);border-color:var(--green);color:var(--green)}}
.chip[data-type="Annual Discount"].active{{background:var(--orange-dim);border-color:var(--orange);color:var(--orange)}}
.chip[data-type="Free Trial"].active{{background:var(--blue-dim);border-color:var(--blue);color:var(--blue)}}
.divider{{width:1px;height:20px;background:var(--border);margin:0 4px}}
.results-meta{{max-width:1100px;margin:0 auto;padding:0 24px 16px;font-size:13px;color:var(--dim)}}
.grid{{max-width:1100px;margin:0 auto;padding:0 24px 64px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;display:flex;flex-direction:column;gap:12px;transition:border-color .15s,transform .15s}}
.card:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.card-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}}
.card-name{{font-size:16px;font-weight:700;line-height:1.3}}
.type-badge{{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap;flex-shrink:0}}
.type-ltd{{background:var(--green-dim);color:var(--green)}}.type-discount{{background:var(--orange-dim);color:var(--orange)}}.type-trial{{background:var(--blue-dim);color:var(--blue)}}
.card-desc{{font-size:13px;color:var(--muted);line-height:1.5}}.card-cat{{font-size:11px;color:var(--dim);font-weight:600;letter-spacing:.5px}}
.card-price{{display:flex;align-items:center;gap:10px}}
.price-deal{{font-size:22px;font-weight:800}}.price-original{{font-size:14px;color:var(--dim);text-decoration:line-through}}
.discount-tag{{background:var(--green-dim);color:var(--green);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700}}
.card-btn{{display:block;text-align:center;background:var(--accent-dim);border:1px solid #6366f160;color:var(--accent);padding:10px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none;transition:background .15s;margin-top:auto}}
.card-btn:hover{{background:var(--accent);color:#fff}}
.no-results{{grid-column:1/-1;text-align:center;padding:60px 0;color:var(--dim)}}
footer{{border-top:1px solid var(--border);padding:32px 24px;text-align:center;color:var(--dim);font-size:13px}}
footer a{{color:var(--accent);text-decoration:none}}
@media(max-width:600px){{.nav-links{{display:none}}}}
</style>
</head>
<body>
<nav>
  <a class="logo" href="/">Saas<span>Scout</span></a>
  <div class="nav-links">
    <a href="/docs">API Docs</a>
    <a href="/v1/deals">JSON API</a>
    <a class="api-btn" href="/docs" target="_blank">Try API →</a>
  </div>
</nav>
<section class="hero">
  <div class="badge">● Updated daily · {total} deals live</div>
  <h1>Track <span>SaaS Lifetime Deals</span> &amp; Price Drops</h1>
  <p>Aggregated deals across AI, Marketing, DevTools, Productivity and more. All affiliate-tagged. Free API access.</p>
  <div class="stats">
    <div class="stat"><div class="stat-num">{total}</div><div class="stat-label">DEALS</div></div>
    <div class="stat"><div class="stat-num">8</div><div class="stat-label">CATEGORIES</div></div>
    <div class="stat"><div class="stat-num">24h</div><div class="stat-label">REFRESH</div></div>
  </div>
</section>
<div class="controls">
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input id="search" type="search" placeholder="Search deals — e.g. email, video, seo…" autocomplete="off">
  </div>
  <div class="filter-row">
    <span class="filter-label">CATEGORY</span>
    <button class="chip active" data-cat="All">All</button>
    {cat_chips}
    <div class="divider"></div>
    <span class="filter-label">TYPE</span>
    <button class="chip active" data-type="All">All</button>
    <button class="chip" data-type="Lifetime Deal">LTD</button>
    <button class="chip" data-type="Annual Discount">Discount</button>
    <button class="chip" data-type="Free Trial">Free Trial</button>
  </div>
</div>
<div class="results-meta" id="results-meta">Showing {total} deals</div>
<div class="grid" id="grid">
{cards}
  <div class="no-results" id="no-results" style="display:none"><h3>No deals found</h3><p>Try a different search or filter</p></div>
</div>
<footer>
  <p>SaasScout — SaaS deals aggregated daily &nbsp;·&nbsp;
  <a href="/docs">API Docs</a> &nbsp;·&nbsp;
  <a href="https://github.com/nxtcraft/saasscout" target="_blank">GitHub</a> &nbsp;·&nbsp;
  <a href="https://rapidapi.com/PradeepKumarKesharwani/api/saasscout-saas-deals-and-lifetime-deal-tracker" target="_blank">RapidAPI</a></p>
</footer>
<script>
const cards=Array.from(document.querySelectorAll('.card'));
const meta=document.getElementById('results-meta');
const noRes=document.getElementById('no-results');
let cat='All',type='All',q='';
function filter(){{
  let v=0;
  cards.forEach(c=>{{
    const show=(cat==='All'||c.dataset.cat===cat)&&(type==='All'||c.dataset.type===type)&&(!q||c.dataset.name.includes(q)||c.dataset.desc.includes(q));
    c.style.display=show?'':'none';if(show)v++;
  }});
  meta.textContent='Showing '+v+' deal'+(v!==1?'s':'');
  noRes.style.display=v===0?'':'none';
}}
document.querySelectorAll('.chip[data-cat]').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('.chip[data-cat]').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');cat=b.dataset.cat;filter();
}}));
document.querySelectorAll('.chip[data-type]').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('.chip[data-type]').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');type=b.dataset.type;filter();
}}));
document.getElementById('search').addEventListener('input',e=>{{q=e.target.value.toLowerCase().trim();filter();}});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def homepage():
    deals = _load_deals()
    return HTMLResponse(_render_homepage(deals))


@app.get("/health", tags=["System"])
def health():
    deals = _load_deals()
    from collections import Counter
    cats = Counter(d["category"] for d in deals)
    return {
        "status": "ok",
        "total_deals": len(deals),
        "categories": dict(cats),
        "data_file_exists": DATA_FILE.exists(),
    }


@app.get("/v1/deals", response_model=PaginatedDeals, tags=["Deals"])
def list_deals(
    category: Optional[str] = Query(None, description="Filter: AI | Marketing | DevTools | Productivity | Analytics | Design | Security | Finance"),
    max_price: Optional[float] = Query(None, description="Max deal price in USD (0 = free only)"),
    min_discount: Optional[float] = Query(None, description="Minimum discount % (e.g. 30 = 30%+ off)"),
    deal_type: Optional[str] = Query(None, description="ltd | discount | free_trial"),
    q: Optional[str] = Query(None, description="Keyword search across name and description"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
):
    deals = _load_deals()
    if not deals:
        raise HTTPException(status_code=503, detail="No deal data. Run pipeline.py to populate.")

    deals = _filter(deals, category=category, max_price=max_price,
                    min_discount=min_discount, deal_type=deal_type, q=q)
    deals.sort(key=lambda d: d["discount_percent"], reverse=True)

    total = len(deals)
    start = (page - 1) * per_page
    page_deals = deals[start: start + per_page]

    return PaginatedDeals(total=total, page=page, per_page=per_page, deals=page_deals)


@app.get("/v1/deals/top", response_model=list[Deal], tags=["Deals"])
def top_deals(
    n: int = Query(10, ge=1, le=50, description="Number of top deals to return"),
    deal_type: Optional[str] = Query(None, description="ltd | discount | free_trial"),
):
    """Return top N deals sorted by highest discount."""
    deals = _load_deals()
    if not deals:
        raise HTTPException(status_code=503, detail="No deal data. Run pipeline.py to populate.")
    if deal_type:
        normalised = DEAL_TYPE_MAP.get(deal_type.lower(), deal_type)
        deals = [d for d in deals if d["deal_type"].lower() == normalised.lower()]
    deals.sort(key=lambda d: d["discount_percent"], reverse=True)
    return deals[:n]


@app.get("/v1/deals/{deal_id}", response_model=Deal, tags=["Deals"])
def get_deal(deal_id: str):
    """Fetch a single deal by its ID."""
    for d in _load_deals():
        if d["id"] == deal_id:
            return d
    raise HTTPException(status_code=404, detail=f"Deal '{deal_id}' not found.")


@app.get("/v1/categories", tags=["Meta"])
def list_categories():
    """Summary of available categories with deal counts and type breakdown."""
    from collections import Counter, defaultdict
    deals = _load_deals()
    summary: dict[str, dict] = defaultdict(lambda: {"total": 0, "types": Counter()})
    for d in deals:
        cat = d.get("category", "Other")
        summary[cat]["total"] += 1
        summary[cat]["types"][d["deal_type"]] += 1

    return {
        "categories": [
            {
                "name": cat,
                "total_deals": info["total"],
                "by_type": dict(info["types"]),
            }
            for cat, info in sorted(summary.items(), key=lambda x: -x[1]["total"])
        ]
    }


@app.get("/v1/search", response_model=list[Deal], tags=["Deals"])
def search_deals(
    q: str = Query(..., min_length=2, description="Keyword to search in name and description"),
    limit: int = Query(20, ge=1, le=100),
):
    """Full-text keyword search across deal names and descriptions."""
    deals = _load_deals()
    lower_q = q.lower()
    results = [
        d for d in deals
        if lower_q in d["name"].lower() or lower_q in d["description"].lower()
    ]
    results.sort(key=lambda d: d["discount_percent"], reverse=True)
    return results[:limit]
