"""
Deal ingestion pipeline — fetches, normalises, and persists SaaS deals.

Sources (in priority order):
  1. AppSumo — HTML scrape of public browse page
  2. Dealify — RSS/HTML scrape
  3. Curated seed catalogue (50+ deals, always included)
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin
import os

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
DEALS_FILE = DATA_DIR / "latest_deals.json"
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "saasscout-20")
PARTNER_ID = os.getenv("PARTNER_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI": [r"\bai\b", "gpt", "llm", "machine learning", "artificial intelligence", "chatbot", "automation", "openai"],
    "Marketing": ["marketing", "seo", r"\bemail\b", "crm", "leads", "social media", "outreach", "campaign"],
    "DevTools": ["developer", r"\bapi\b", "devtools", r"\bcode\b", "github", "deployment", "cloud", "hosting", "database", "backend"],
    "Productivity": ["productivity", r"\btask\b", "project management", "notes", "calendar", "collaboration", "workflow", "team"],
    "Analytics": ["analytics", "dashboard", "reporting", "metrics", r"\bdata\b", "insights", "tracking", "heatmap"],
    "Design": ["design", "figma", "ui", "ux", "prototype", "wireframe", "graphic", "video", "image"],
    "Security": ["security", "vpn", "password", "2fa", "authentication", "firewall", "privacy"],
    "Finance": ["finance", "accounting", "invoicing", "billing", "payment", "bookkeeping", "tax"],
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _deal_id(name: str, source: str) -> str:
    return hashlib.md5(f"{source}:{name}".encode()).hexdigest()[:12]


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


def _parse_price(text: str) -> float:
    cleaned = text.replace(",", "").replace("$", "").strip()
    match = re.search(r"\d+\.?\d*", cleaned)
    return float(match.group()) if match else 0.0


def _affiliate_url(url: str, source: str = "") -> str:
    if not url:
        return url
    params: dict[str, str] = {"ref": AFFILIATE_TAG}
    if PARTNER_ID:
        params["partner"] = PARTNER_ID
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode(params)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_deal(
    name: str,
    source: str,
    url: str,
    original: float,
    deal_p: float,
    deal_type: str,
    description: str = "",
    category: str = "",
) -> dict:
    return {
        "id": _deal_id(name, source),
        "name": name,
        "category": category or _classify(name + " " + description),
        "original_price": round(original, 2),
        "deal_price": round(deal_p, 2),
        "discount_percent": _discount(original, deal_p),
        "deal_type": deal_type,
        "affiliate_url": _affiliate_url(url, source),
        "description": description[:400],
        "source": source,
        "discovered_at": _now(),
    }


# ---------------------------------------------------------------------------
# Source 1 — AppSumo (HTML scrape)
# ---------------------------------------------------------------------------

def _fetch_appsumo(client: httpx.Client) -> list[dict]:
    deals: list[dict] = []
    try:
        resp = client.get(
            "https://appsumo.com/browse/?ordering=-published_at",
            headers=HEADERS,
            timeout=20,
        )
        soup = BeautifulSoup(resp.text, "lxml")

        # AppSumo uses React; try JSON-LD or data attributes first
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                products = []
                if isinstance(data, list):
                    products = data
                elif isinstance(data, dict):
                    products = data.get("products", data.get("results", []))
                for p in products[:30]:
                    name = p.get("name") or p.get("title") or ""
                    if not name:
                        continue
                    original = float(p.get("original_price") or p.get("regular_price") or 0)
                    deal_p = float(p.get("current_price") or p.get("sale_price") or original)
                    url = p.get("url") or p.get("deal_url") or f"https://appsumo.com/products/{_slug(name)}/"
                    if not url.startswith("http"):
                        url = urljoin("https://appsumo.com", url)
                    desc = str(p.get("description") or p.get("tagline") or "")[:400]
                    deals.append(_make_deal(name, "appsumo", url, original, deal_p, "Lifetime Deal", desc))
            except Exception:
                continue

        # Fallback: scrape visible deal cards
        if not deals:
            cards = soup.select(
                "div[data-gatsby-image-wrapper] ~ div, "
                "article[class*='product'], div[class*='product-card'], "
                "div[class*='deal-card'], li[class*='deal']"
            )
            for card in cards[:20]:
                title = card.select_one("h3, h2, [class*='title'], [class*='name']")
                name = title.get_text(strip=True) if title else ""
                if len(name) < 3:
                    continue
                link = card.select_one("a[href]")
                url = urljoin("https://appsumo.com", link["href"]) if link else "https://appsumo.com"
                price_els = card.select("[class*='price']")
                prices = [_parse_price(el.get_text()) for el in price_els if _parse_price(el.get_text()) > 0]
                deal_p = min(prices) if prices else 0.0
                original = max(prices) if len(prices) > 1 else deal_p
                desc_el = card.select_one("p, [class*='description'], [class*='tagline']")
                desc = desc_el.get_text(strip=True)[:400] if desc_el else ""
                deals.append(_make_deal(name, "appsumo", url, original, deal_p, "Lifetime Deal", desc))
    except Exception as e:
        print(f"[appsumo] scrape failed: {e}")
    return deals


# ---------------------------------------------------------------------------
# Source 2 — Dealify (RSS)
# ---------------------------------------------------------------------------

DEALIFY_RSS = "https://dealify.com/blogs/news.atom"


def _fetch_dealify(client: httpx.Client) -> list[dict]:
    deals: list[dict] = []
    try:
        resp = client.get(DEALIFY_RSS, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml-xml")
        for entry in soup.find_all("entry")[:20]:
            title = entry.find("title")
            name = title.get_text(strip=True) if title else ""
            if not name:
                continue
            link = entry.find("link")
            url = (link.get("href") or link.get_text(strip=True)) if link else "https://dealify.com"
            summary = entry.find("summary") or entry.find("content")
            desc = BeautifulSoup(summary.get_text(), "lxml").get_text(strip=True)[:400] if summary else ""
            deals.append(_make_deal(name, "dealify", url, 0.0, 0.0, "Lifetime Deal", desc))
    except Exception as e:
        print(f"[dealify] fetch failed: {e}")
    return deals


# ---------------------------------------------------------------------------
# Source 3 — Curated seed catalogue (50+ deals)
# ---------------------------------------------------------------------------

SEED_CATALOGUE = [
    # ── Lifetime Deals (real LTDs with one-time price) ──────────────────────
    ("Cleanshot X", "Design", 59.0, 29.0, "Lifetime Deal", "https://cleanshot.com", "Screenshot, screen recording, and annotation app for Mac. One-time purchase, lifetime updates."),
    ("Supercreator AI", "AI", 199.0, 69.0, "Lifetime Deal", "https://supercreator.ai", "AI short-video scripting tool. Generates hooks, scripts, and captions for TikTok/Reels."),
    ("Screenpipe", "Productivity", 99.0, 49.0, "Lifetime Deal", "https://screenpi.pe", "Local-first screen and audio recorder with AI search — find anything you've seen on screen."),
    ("SocialBee", "Marketing", 828.0, 99.0, "Lifetime Deal", "https://socialbee.com", "Social media scheduling with AI-powered content categories and recycling. AppSumo LTD."),
    ("Writecream", "AI", 588.0, 49.0, "Lifetime Deal", "https://writecream.com", "AI content generator for blogs, cold emails, LinkedIn, and voiceovers. AppSumo LTD."),
    ("Taplio", "Marketing", 588.0, 99.0, "Lifetime Deal", "https://taplio.com", "LinkedIn content and growth tool with AI post generator and CRM. Lifetime AppSumo deal."),
    ("MeetGeek", "Productivity", 576.0, 79.0, "Lifetime Deal", "https://meetgeek.ai", "AI meeting recorder that auto-transcribes, summarises, and extracts action items."),
    ("Formaloo", "Productivity", 588.0, 69.0, "Lifetime Deal", "https://formaloo.com", "No-code form builder and CRM with portals, quizzes, and automations. AppSumo LTD."),
    ("Sendster", "Marketing", 588.0, 59.0, "Lifetime Deal", "https://sendster.com", "Self-hosted email marketing platform — unlimited subscribers, no monthly fees."),
    ("Pabbly Connect", "Productivity", 1188.0, 249.0, "Lifetime Deal", "https://pabbly.com/connect", "Automation platform connecting 1000+ apps. One-time price, unlimited workflows."),
    ("TidyCal", "Productivity", 576.0, 29.0, "Lifetime Deal", "https://tidycal.com", "Simple appointment booking tool by AppSumo. One-time $29, unlimited bookings forever."),
    ("Hostinger Website Builder", "DevTools", 299.0, 69.0, "Lifetime Deal", "https://hostinger.com", "AI website builder with built-in hosting — create a professional site in minutes."),
    ("Coupler.io", "Analytics", 588.0, 89.0, "Lifetime Deal", "https://coupler.io", "No-code data integration platform pulling data from APIs into Google Sheets, Looker Studio."),
    ("SerpApi", "DevTools", 588.0, 79.0, "Lifetime Deal", "https://serpapi.com", "Real-time Google Search API for scraping SERPs — lifetime deal via AppSumo."),
    ("Uxcel", "Design", 299.0, 49.0, "Lifetime Deal", "https://uxcel.com", "UX design skills platform with interactive courses, challenges, and assessments."),
    ("Landbot", "Marketing", 588.0, 89.0, "Lifetime Deal", "https://landbot.io", "No-code chatbot builder for landing pages, WhatsApp, and web — past AppSumo LTD."),
    ("Mailmodo", "Marketing", 1188.0, 119.0, "Lifetime Deal", "https://mailmodo.com", "AMP email marketing platform — send interactive emails with forms, carts, and widgets."),
    ("Scalenut", "AI", 588.0, 79.0, "Lifetime Deal", "https://scalenut.com", "AI SEO content platform: keyword research, briefs, writing, and optimization in one."),
    ("Jasper (LTD era)", "AI", 588.0, 49.0, "Lifetime Deal", "https://jasper.ai", "AI writing assistant for long-form blogs and marketing copy — early LTD cohort pricing."),
    ("Dyluno", "Analytics", 299.0, 49.0, "Lifetime Deal", "https://dyluno.com", "Heatmaps, session recordings, and conversion analytics. Lifetime deal via AppSumo."),

    # ── Annual Discounts (real percentage-off deals) ─────────────────────────
    ("Ahrefs", "Marketing", 129.0, 99.0, "Annual Discount", "https://ahrefs.com", "All-in-one SEO toolset: backlinks, keywords, content explorer, and site audits."),
    ("Semrush", "Marketing", 139.95, 99.95, "Annual Discount", "https://semrush.com", "SEO, PPC, content marketing, and competitor research platform."),
    ("Surfer SEO", "Marketing", 89.0, 59.0, "Annual Discount", "https://surferseo.com", "AI-powered on-page SEO scoring and content optimization tool."),
    ("Writesonic", "AI", 99.0, 16.0, "Annual Discount", "https://writesonic.com", "AI writing platform for blogs, ads, and landing pages. 84% off annual plan."),
    ("Jasper AI", "AI", 59.0, 39.0, "Annual Discount", "https://jasper.ai", "AI content platform for marketing teams — 33% off annual billing."),
    ("Pictory", "AI", 99.0, 49.0, "Annual Discount", "https://pictory.ai", "Turn blog posts and scripts into short branded videos. 50% off annual."),
    ("Murf AI", "AI", 39.0, 19.0, "Annual Discount", "https://murf.ai", "Studio-quality AI voice generator with 120+ voices and 20 languages."),
    ("Descript", "AI", 24.0, 12.0, "Annual Discount", "https://descript.com", "AI video and podcast editor with overdub voice cloning. 50% off annual."),
    ("Hunter.io", "Marketing", 49.0, 34.0, "Annual Discount", "https://hunter.io", "Find and verify professional email addresses — 30% off annual plan."),
    ("Lemlist", "Marketing", 99.0, 59.0, "Annual Discount", "https://lemlist.com", "Cold email and LinkedIn outreach automation — 40% off annual plan."),
    ("Instantly", "Marketing", 97.0, 37.0, "Annual Discount", "https://instantly.ai", "AI cold email outreach with unlimited sending accounts — 62% off annual."),
    ("Uploadcare", "DevTools", 49.0, 29.0, "Annual Discount", "https://uploadcare.com", "File upload, transformation, and CDN delivery — 41% off annual plan."),
    ("Obsidian", "Productivity", 8.0, 4.0, "Annual Discount", "https://obsidian.md", "Private, local-first markdown note-taking with plugin ecosystem."),
    ("NordVPN", "Security", 11.99, 3.99, "Annual Discount", "https://nordvpn.com", "Fast, secure VPN — 67% off 2-year plan with 5500+ servers in 60 countries."),
    ("Railway", "DevTools", 20.0, 5.0, "Annual Discount", "https://railway.app", "Deploy apps and databases instantly from GitHub — 75% off annual."),

    # ── Free Trials (tools with generous free tiers worth promoting) ─────────
    ("Beehiiv", "Marketing", 42.0, 0.0, "Free Trial", "https://beehiiv.com", "Newsletter platform with built-in ad network and growth tools. Free up to 2,500 subs."),
    ("Supabase", "DevTools", 25.0, 0.0, "Free Trial", "https://supabase.com", "Open-source Firebase alternative with Postgres, auth, storage, and real-time."),
    ("PostHog", "Analytics", 0.0, 0.0, "Free Trial", "https://posthog.com", "Open-source product analytics with feature flags and session recordings. 1M events free."),
    ("Plausible Analytics", "Analytics", 9.0, 0.0, "Free Trial", "https://plausible.io", "Lightweight, privacy-first web analytics. No cookies, GDPR compliant, 30-day trial."),
    ("Fathom Analytics", "Analytics", 14.0, 0.0, "Free Trial", "https://usefathom.com", "Simple, privacy-respecting website analytics. GDPR compliant, 7-day free trial."),
    ("Lemon Squeezy", "Finance", 0.0, 0.0, "Free Trial", "https://lemonsqueezy.com", "Merchant of record for SaaS — handles global tax, subscriptions, and payouts. Free to start."),
]


def _build_seed_deals() -> list[dict]:
    result = []
    for row in SEED_CATALOGUE:
        name, category, original, deal_p, deal_type, url, desc = row
        result.append(_make_deal(name, "seed", url, original, deal_p, deal_type, desc, category))
    return result


# ---------------------------------------------------------------------------
# Deduplication & sorting
# ---------------------------------------------------------------------------

def _deduplicate(deals: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for d in deals:
        key = d["id"]
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_pipeline() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)

    with httpx.Client(follow_redirects=True) as client:
        appsumo = _fetch_appsumo(client)
        dealify = _fetch_dealify(client)

    seed = _build_seed_deals()

    print(f"[pipeline] appsumo={len(appsumo)} dealify={len(dealify)} seed={len(seed)}")

    all_deals = appsumo + dealify + seed
    all_deals = _deduplicate(all_deals)
    all_deals.sort(key=lambda d: d["discount_percent"], reverse=True)

    DEALS_FILE.write_text(json.dumps(all_deals, indent=2))
    print(f"[pipeline] Saved {len(all_deals)} deals → {DEALS_FILE}")
    return all_deals


if __name__ == "__main__":
    run_pipeline()
