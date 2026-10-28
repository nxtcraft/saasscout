# SaasScout — SaaS Deals & Lifetime Deal Tracker API

Real-time aggregated SaaS promotions, lifetime deals, and price drops — auto-updated daily, affiliate-tagged, served via FastAPI.

## Live Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System status + deal count |
| GET | `/v1/deals` | Paginated deals with filters |
| GET | `/v1/deals/top` | Top N deals by discount |
| GET | `/v1/deals/{id}` | Single deal by ID |
| GET | `/v1/categories` | Category summary with type breakdown |
| GET | `/v1/search?q=...` | Keyword search across name + description |

Interactive docs: `/docs` · `/redoc`

## Query Parameters — `/v1/deals`

| Param | Type | Example |
|-------|------|---------|
| `category` | string | `AI`, `Marketing`, `DevTools`, `Productivity`, `Analytics`, `Design`, `Security`, `Finance` |
| `deal_type` | string | `ltd`, `discount`, `free_trial` |
| `max_price` | float | `0` (free only), `29` |
| `min_discount` | float | `30` (30%+ off) |
| `q` | string | `email`, `seo`, `video` |
| `page` | int | `1` |
| `per_page` | int | `20` (max 100) |

## Example Requests

```bash
# All lifetime deals
GET /v1/deals?deal_type=ltd

# Free AI tools
GET /v1/deals?category=AI&max_price=0

# 30%+ off Marketing tools
GET /v1/deals?category=Marketing&min_discount=30

# Search for video tools
GET /v1/search?q=video

# Top 5 biggest discounts
GET /v1/deals/top?n=5
```

## Example Response

```json
{
  "total": 53,
  "page": 1,
  "per_page": 20,
  "deals": [
    {
      "id": "a1b2c3d4e5f6",
      "name": "Writesonic",
      "category": "AI",
      "original_price": 49.0,
      "deal_price": 16.0,
      "discount_percent": 67.3,
      "deal_type": "Annual Discount",
      "affiliate_url": "https://writesonic.com?ref=saasscout-20",
      "description": "AI writing assistant for blogs, ads, emails, and landing pages.",
      "source": "seed",
      "discovered_at": "2026-10-28T00:00:00+00:00"
    }
  ]
}
```

## Local Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline.py          # populate data/latest_deals.json
uvicorn main:app --reload   # start API at http://localhost:8000
pytest test_pipeline.py -v  # run tests
```

## Deploy to Render

1. Connect this repo at **render.com**
2. `render.yaml` auto-configures everything
3. Set env vars: `AFFILIATE_TAG`, `PARTNER_ID`

## Data Sources

- **AppSumo** — HTML scrape of daily lifetime deals
- **Dealify** — RSS feed of curated SaaS deals  
- **Curated catalogue** — 53 hand-picked SaaS tools with real pricing

## Affiliate Networks

Sign up and replace `AFFILIATE_TAG` with your real IDs:
- [AppSumo Affiliates](https://appsumo.com/affiliates) — $50–$100 per sale
- [PartnerStack](https://partnerstack.com) — 20–40% recurring
- [Impact.com](https://impact.com) — hundreds of SaaS brands
