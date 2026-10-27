"""
SaasScout API — exposes aggregated SaaS deals and lifetime software discounts.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel

DATA_FILE = Path(__file__).parent / "data" / "latest_deals.json"

app = FastAPI(
    title="SaasScout — SaaS Deals & Lifetime Deal Tracker",
    description="Aggregated SaaS promotions, lifetime deals, and price drops with affiliate-tagged links.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


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
    discovered_at: str


def _load_deals() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


@app.get("/health")
def health():
    deals = _load_deals()
    return {
        "status": "ok",
        "total_deals": len(deals),
        "data_file": str(DATA_FILE),
        "data_exists": DATA_FILE.exists(),
    }


@app.get("/v1/deals", response_model=list[Deal])
def list_deals(
    category: Optional[str] = Query(None, description="Filter by category (AI, Marketing, DevTools, Productivity, Analytics)"),
    max_price: Optional[float] = Query(None, description="Maximum deal price in USD"),
    deal_type: Optional[str] = Query(None, description="ltd | discount | free_trial"),
    limit: int = Query(50, ge=1, le=200, description="Max number of results"),
):
    deals = _load_deals()

    if not deals:
        raise HTTPException(status_code=503, detail="No deal data available. Run pipeline.py to populate.")

    # Normalise deal_type filter
    TYPE_MAP = {
        "ltd": "Lifetime Deal",
        "lifetime": "Lifetime Deal",
        "discount": "Annual Discount",
        "annual": "Annual Discount",
        "free_trial": "Free Trial",
        "free": "Free Trial",
        "trial": "Free Trial",
    }

    if category:
        deals = [d for d in deals if d["category"].lower() == category.lower()]
    if max_price is not None:
        deals = [d for d in deals if d["deal_price"] <= max_price]
    if deal_type:
        normalised = TYPE_MAP.get(deal_type.lower(), deal_type)
        deals = [d for d in deals if d["deal_type"].lower() == normalised.lower()]

    # Default sort: highest discount first
    deals.sort(key=lambda d: d["discount_percent"], reverse=True)

    return deals[:limit]


@app.get("/v1/categories")
def list_categories():
    deals = _load_deals()
    summary: dict[str, int] = {}
    for d in deals:
        cat = d.get("category", "Other")
        summary[cat] = summary.get(cat, 0) + 1
    return {
        "categories": [
            {"name": cat, "deal_count": count}
            for cat, count in sorted(summary.items(), key=lambda x: -x[1])
        ]
    }


@app.get("/v1/deals/{deal_id}", response_model=Deal)
def get_deal(deal_id: str):
    deals = _load_deals()
    for d in deals:
        if d["id"] == deal_id:
            return d
    raise HTTPException(status_code=404, detail=f"Deal '{deal_id}' not found.")
