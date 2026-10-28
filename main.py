"""SaasScout API — aggregated SaaS deals, lifetime offers, and price drops."""

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

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

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def homepage(request: Request):
    deals = _load_deals()
    categories = sorted(set(d["category"] for d in deals))
    return templates.TemplateResponse("index.html", {
        "request": request,
        "deals": deals,
        "total": len(deals),
        "categories": categories,
    })


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
