"""
Deal ingestion pipeline — fetches, normalises, and persists SaaS deals.

Sources:
  1. AppSumo public RSS feed
  2. Product Hunt "deals" tag via public GraphQL endpoint
  3. Fallback seed deals (always included so the API is never empty)
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs, urljoin

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
DEALS_FILE = DATA_DIR / "latest_deals.json"
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "saasscout-20")
PARTNER_ID = os.getenv("PARTNER_ID", "")

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI": [r"\bai\b", "gpt", "llm", "machine learning", "artificial intelligence", "chatbot", "automation"],
    "Marketing": ["marketing", "seo", r"\bemail\b", "crm", "leads", "social media"],
    "DevTools": ["developer", r"\bapi\b", "devtools", r"\bcode\b", "github", "deployment", "cloud", "hosting"],
    "Productivity": ["productivity", r"\btask\b", "project management", "notes", "calendar", "collaboration"],
    "Analytics": ["analytics", "dashboard", "reporting", "metrics", r"\bdata\b", "insights", "tracking"],
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _deal_id(name: str, source: str) -> str:
    raw = f"{source}:{name}".encode()
    return hashlib.md5(raw).hexdigest()[:12]


def _classify(text: str) -> str:
    lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            pattern = kw if kw.startswith(r"\b") else re.escape(kw)
            if re.search(pattern, lower):
                return category
    return "Other"


def _discount(original: float, deal: float) -> float:
    if original <= 0 or deal >= original:
        return 0.0
    return round((original - deal) / original * 100, 1)


def _affiliate_url(url: str) -> str:
    """Append affiliate/tracking params to the destination URL."""
    if not url:
        return url
    sep = "&" if "?" in url else "?"
    params: dict[str, str] = {"ref": AFFILIATE_TAG}
    if PARTNER_ID:
        params["partner"] = PARTNER_ID
    return f"{url}{sep}{urlencode(params)}"


# ---------------------------------------------------------------------------
# Source 1 — AppSumo RSS
# ---------------------------------------------------------------------------

APPSUMO_RSS = "https://appsumo.com/products/?ordering=-published_at&format=json"
APPSUMO_RSS_FALLBACK = "https://feeds.feedburner.com/AppSumoDeals"


def _fetch_appsumo(client: httpx.Client) -> list[dict]:
    deals: list[dict] = []

    # Try the JSON product listing first
    try:
        resp = client.get(
            "https://appsumo.com/products/?ordering=-published_at&format=json",
            timeout=15,
            headers={"Accept": "application/json", "User-Agent": "SaasScout/1.0"},
        )
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            products = data.get("results", data) if isinstance(data, dict) else data
            for p in products[:30]:
                name = p.get("name") or p.get("title") or ""
                if not name:
                    continue
                original = float(p.get("original_price") or p.get("price") or 0)
                deal_p = float(p.get("current_price") or p.get("deal_price") or original)
                url = p.get("url") or p.get("deal_url") or f"https://appsumo.com/products/{_slug(name)}/"
                deals.append({
                    "id": _deal_id(name, "appsumo"),
                    "name": name,
                    "category": _classify(name + " " + str(p.get("description", ""))),
                    "original_price": original,
                    "deal_price": deal_p,
                    "discount_percent": _discount(original, deal_p),
                    "deal_type": "Lifetime Deal",
                    "affiliate_url": _affiliate_url(url if url.startswith("http") else urljoin("https://appsumo.com", url)),
                    "description": str(p.get("description", ""))[:300],
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                })
            return deals
    except Exception:
        pass

    # Fallback: scrape the HTML listing page
    try:
        resp = client.get(
            "https://appsumo.com/browse/?ordering=-published_at",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 SaasScout/1.0"},
        )
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div[data-deal-name], article.deal-card, div.product-card")
        for card in cards[:20]:
            name = (
                card.get("data-deal-name")
                or (card.select_one("h3, h2, .deal-title, .product-title") or {}).get_text(strip=True)
                or ""
            )
            if not name:
                continue
            link_tag = card.select_one("a[href]")
            url = urljoin("https://appsumo.com", link_tag["href"]) if link_tag else "https://appsumo.com"
            price_tag = card.select_one(".price, .deal-price, [class*='price']")
            deal_p = _parse_price(price_tag.get_text() if price_tag else "0")
            original_tag = card.select_one(".original-price, .was-price, [class*='original']")
            original = _parse_price(original_tag.get_text() if original_tag else "0") or deal_p
            desc_tag = card.select_one("p, .description, .deal-description")
            desc = desc_tag.get_text(strip=True)[:300] if desc_tag else ""
            deals.append({
                "id": _deal_id(name, "appsumo"),
                "name": name,
                "category": _classify(name + " " + desc),
                "original_price": original,
                "deal_price": deal_p,
                "discount_percent": _discount(original, deal_p),
                "deal_type": "Lifetime Deal",
                "affiliate_url": _affiliate_url(url),
                "description": desc,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception:
        pass

    return deals


# ---------------------------------------------------------------------------
# Source 2 — Product Hunt "deals" / "software" tag
# ---------------------------------------------------------------------------

PH_GQL_URL = "https://api.producthunt.com/v2/api/graphql"

PH_QUERY = """
{
  posts(order: VOTES, topic: "software-deals", first: 20) {
    edges {
      node {
        name
        tagline
        url
        votesCount
        topics { edges { node { name } } }
        thumbnail { url }
      }
    }
  }
}
"""


def _fetch_producthunt(client: httpx.Client) -> list[dict]:
    deals: list[dict] = []
    try:
        resp = client.post(
            PH_GQL_URL,
            json={"query": PH_QUERY},
            timeout=15,
            headers={"Content-Type": "application/json", "User-Agent": "SaasScout/1.0"},
        )
        if resp.status_code != 200:
            return deals
        posts = resp.json().get("data", {}).get("posts", {}).get("edges", [])
        for edge in posts:
            node = edge.get("node", {})
            name = node.get("name", "")
            if not name:
                continue
            url = node.get("url") or f"https://www.producthunt.com/posts/{_slug(name)}"
            topics = [t["node"]["name"] for t in node.get("topics", {}).get("edges", [])]
            deals.append({
                "id": _deal_id(name, "producthunt"),
                "name": name,
                "category": _classify(" ".join([name, node.get("tagline", "")] + topics)),
                "original_price": 0.0,
                "deal_price": 0.0,
                "discount_percent": 0.0,
                "deal_type": "Free Trial",
                "affiliate_url": _affiliate_url(url),
                "description": node.get("tagline", "")[:300],
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception:
        pass
    return deals


# ---------------------------------------------------------------------------
# Source 3 — Seed / fallback deals (always present)
# ---------------------------------------------------------------------------

SEED_DEALS = [
    {
        "name": "Notion",
        "category": "Productivity",
        "original_price": 16.0,
        "deal_price": 0.0,
        "deal_type": "Free Trial",
        "url": "https://notion.so",
        "description": "All-in-one workspace for notes, docs, and project management.",
    },
    {
        "name": "Ahrefs",
        "category": "Marketing",
        "original_price": 99.0,
        "deal_price": 7.0,
        "deal_type": "Annual Discount",
        "url": "https://ahrefs.com",
        "description": "SEO toolset for backlinks, keyword research, and site audits.",
    },
    {
        "name": "Screaming Frog SEO Spider",
        "category": "Marketing",
        "original_price": 259.0,
        "deal_price": 199.0,
        "deal_type": "Annual Discount",
        "url": "https://screamingfrog.co.uk/seo-spider",
        "description": "Desktop crawler for technical SEO analysis.",
    },
    {
        "name": "Fathom Analytics",
        "category": "Analytics",
        "original_price": 14.0,
        "deal_price": 0.0,
        "deal_type": "Free Trial",
        "url": "https://usefathom.com",
        "description": "Privacy-first, GDPR-compliant website analytics.",
    },
    {
        "name": "Plausible Analytics",
        "category": "Analytics",
        "original_price": 9.0,
        "deal_price": 0.0,
        "deal_type": "Free Trial",
        "url": "https://plausible.io",
        "description": "Lightweight, open-source web analytics.",
    },
    {
        "name": "Supercreator AI",
        "category": "AI",
        "original_price": 49.0,
        "deal_price": 29.0,
        "deal_type": "Lifetime Deal",
        "url": "https://supercreator.ai",
        "description": "AI-powered short video creation and scripting tool.",
    },
    {
        "name": "Writesonic",
        "category": "AI",
        "original_price": 49.0,
        "deal_price": 15.0,
        "deal_type": "Annual Discount",
        "url": "https://writesonic.com",
        "description": "AI writing assistant for blogs, ads, and landing pages.",
    },
    {
        "name": "Huly",
        "category": "Productivity",
        "original_price": 12.0,
        "deal_price": 0.0,
        "deal_type": "Free Trial",
        "url": "https://huly.io",
        "description": "Open-source project management and team collaboration.",
    },
    {
        "name": "Pika",
        "category": "AI",
        "original_price": 35.0,
        "deal_price": 8.0,
        "deal_type": "Annual Discount",
        "url": "https://pika.art",
        "description": "AI video generation from text and images.",
    },
    {
        "name": "Supabase",
        "category": "DevTools",
        "original_price": 25.0,
        "deal_price": 0.0,
        "deal_type": "Free Trial",
        "url": "https://supabase.com",
        "description": "Open-source Firebase alternative with Postgres backend.",
    },
]


def _build_seed_deals() -> list[dict]:
    result = []
    for s in SEED_DEALS:
        result.append({
            "id": _deal_id(s["name"], "seed"),
            "name": s["name"],
            "category": s["category"],
            "original_price": s["original_price"],
            "deal_price": s["deal_price"],
            "discount_percent": _discount(s["original_price"], s["deal_price"]),
            "deal_type": s["deal_type"],
            "affiliate_url": _affiliate_url(s["url"]),
            "description": s["description"],
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        })
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> float:
    match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            pass
    return 0.0


def _deduplicate(deals: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for d in deals:
        if d["id"] not in seen:
            seen.add(d["id"])
            unique.append(d)
    return unique


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_pipeline() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)

    with httpx.Client(follow_redirects=True) as client:
        appsumo = _fetch_appsumo(client)
        ph = _fetch_producthunt(client)

    seed = _build_seed_deals()

    all_deals = appsumo + ph + seed
    all_deals = _deduplicate(all_deals)
    all_deals.sort(key=lambda d: d["discount_percent"], reverse=True)

    DEALS_FILE.write_text(json.dumps(all_deals, indent=2))
    print(f"[pipeline] Saved {len(all_deals)} deals → {DEALS_FILE}")
    return all_deals


if __name__ == "__main__":
    run_pipeline()
