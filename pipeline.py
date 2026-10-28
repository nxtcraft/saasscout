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
    # AI Tools
    ("Writesonic", "AI", 49.0, 16.0, "Annual Discount", "https://writesonic.com", "AI writing assistant for blogs, ads, emails, and landing pages."),
    ("Jasper AI", "AI", 59.0, 39.0, "Annual Discount", "https://jasper.ai", "AI content platform for marketing teams."),
    ("Copy.ai", "AI", 49.0, 0.0, "Free Trial", "https://copy.ai", "AI copywriting tool for social, ads, and long-form content."),
    ("Supercreator AI", "AI", 49.0, 29.0, "Lifetime Deal", "https://supercreator.ai", "AI-powered short video scripting and creation."),
    ("Pictory", "AI", 99.0, 49.0, "Annual Discount", "https://pictory.ai", "Turn blog posts and scripts into short branded videos."),
    ("Murf AI", "AI", 39.0, 19.0, "Annual Discount", "https://murf.ai", "Studio-quality AI voice generator with 120+ voices."),
    ("Descript", "AI", 24.0, 12.0, "Annual Discount", "https://descript.com", "AI video and podcast editor with overdub voice cloning."),
    ("Pika", "AI", 35.0, 8.0, "Annual Discount", "https://pika.art", "AI video generation from text and images."),
    ("Runway ML", "AI", 15.0, 0.0, "Free Trial", "https://runwayml.com", "AI video editing, generation, and VFX tools."),
    ("ElevenLabs", "AI", 22.0, 0.0, "Free Trial", "https://elevenlabs.io", "Ultra-realistic AI voice cloning and synthesis."),
    ("Synthesia", "AI", 30.0, 0.0, "Free Trial", "https://synthesia.io", "Create AI avatar videos without cameras or crews."),

    # Marketing
    ("Ahrefs", "Marketing", 129.0, 99.0, "Annual Discount", "https://ahrefs.com", "All-in-one SEO toolset: backlinks, keywords, site audits."),
    ("Semrush", "Marketing", 139.95, 99.95, "Annual Discount", "https://semrush.com", "SEO, PPC, content, and competitive research platform."),
    ("Surfer SEO", "Marketing", 89.0, 59.0, "Annual Discount", "https://surferseo.com", "AI-powered on-page SEO optimisation and content scoring."),
    ("Mailchimp", "Marketing", 20.0, 0.0, "Free Trial", "https://mailchimp.com", "Email marketing and automation for small businesses."),
    ("ConvertKit", "Marketing", 29.0, 0.0, "Free Trial", "https://convertkit.com", "Email platform for creators with powerful automation."),
    ("Beehiiv", "Marketing", 42.0, 0.0, "Free Trial", "https://beehiiv.com", "Newsletter platform built for growth with ad network."),
    ("Hunter.io", "Marketing", 49.0, 34.0, "Annual Discount", "https://hunter.io", "Find and verify professional email addresses at scale."),
    ("Lemlist", "Marketing", 99.0, 59.0, "Annual Discount", "https://lemlist.com", "Cold email and LinkedIn outreach automation."),
    ("Instantly", "Marketing", 97.0, 37.0, "Annual Discount", "https://instantly.ai", "AI cold email outreach with unlimited sending accounts."),

    # DevTools
    ("Supabase", "DevTools", 25.0, 0.0, "Free Trial", "https://supabase.com", "Open-source Firebase alternative with Postgres backend."),
    ("Railway", "DevTools", 20.0, 5.0, "Annual Discount", "https://railway.app", "Deploy apps and databases instantly from GitHub."),
    ("Render", "DevTools", 25.0, 0.0, "Free Trial", "https://render.com", "Cloud hosting for web services, static sites, and databases."),
    ("PlanetScale", "DevTools", 29.0, 0.0, "Free Trial", "https://planetscale.com", "Serverless MySQL platform with branching workflow."),
    ("Neon", "DevTools", 19.0, 0.0, "Free Trial", "https://neon.tech", "Serverless Postgres with branching for development."),
    ("Retool", "DevTools", 10.0, 0.0, "Free Trial", "https://retool.com", "Low-code platform for building internal tools fast."),
    ("Appwrite", "DevTools", 15.0, 0.0, "Free Trial", "https://appwrite.io", "Open-source backend platform for web and mobile apps."),
    ("Doppler", "DevTools", 0.0, 0.0, "Free Trial", "https://doppler.com", "Universal secrets manager for environment variables."),
    ("Uploadcare", "DevTools", 49.0, 29.0, "Annual Discount", "https://uploadcare.com", "File upload and CDN delivery infrastructure for apps."),

    # Productivity
    ("Notion", "Productivity", 16.0, 0.0, "Free Trial", "https://notion.so", "All-in-one workspace for notes, docs, and project management."),
    ("Coda", "Productivity", 12.0, 0.0, "Free Trial", "https://coda.io", "Docs that think like apps — combine data and narrative."),
    ("ClickUp", "Productivity", 12.0, 0.0, "Free Trial", "https://clickup.com", "All-in-one project management and productivity platform."),
    ("Linear", "Productivity", 8.0, 0.0, "Free Trial", "https://linear.app", "Fast, modern issue tracker for software teams."),
    ("Huly", "Productivity", 12.0, 0.0, "Free Trial", "https://huly.io", "Open-source all-in-one project and team management."),
    ("Todoist", "Productivity", 8.0, 0.0, "Free Trial", "https://todoist.com", "Task manager and to-do list for busy professionals."),
    ("Obsidian", "Productivity", 8.0, 4.0, "Annual Discount", "https://obsidian.md", "Private, local-first markdown note-taking with plugins."),
    ("Tana", "Productivity", 14.0, 0.0, "Free Trial", "https://tana.inc", "Supertag-based outliner for knowledge management."),

    # Analytics
    ("Fathom Analytics", "Analytics", 14.0, 0.0, "Free Trial", "https://usefathom.com", "Privacy-first, GDPR-compliant website analytics."),
    ("Plausible Analytics", "Analytics", 9.0, 0.0, "Free Trial", "https://plausible.io", "Lightweight, open-source privacy-focused web analytics."),
    ("Heap", "Analytics", 0.0, 0.0, "Free Trial", "https://heap.io", "Auto-capture every user interaction for product analytics."),
    ("Hotjar", "Analytics", 32.0, 0.0, "Free Trial", "https://hotjar.com", "Heatmaps, session recordings, and user surveys."),
    ("PostHog", "Analytics", 0.0, 0.0, "Free Trial", "https://posthog.com", "Open-source product analytics and feature flags."),
    ("Mixpanel", "Analytics", 28.0, 0.0, "Free Trial", "https://mixpanel.com", "Event-based product analytics for growth teams."),

    # Design
    ("Canva", "Design", 15.0, 0.0, "Free Trial", "https://canva.com", "Drag-and-drop graphic design for non-designers."),
    ("Framer", "Design", 20.0, 0.0, "Free Trial", "https://framer.com", "Design and publish high-performance websites visually."),
    ("Loom", "Design", 15.0, 0.0, "Free Trial", "https://loom.com", "Async video messaging for teams and client walkthroughs."),
    ("Cleanshot X", "Design", 29.0, 19.0, "Lifetime Deal", "https://cleanshot.com", "Screenshot and screen recording app for Mac."),

    # Security
    ("1Password", "Security", 7.99, 0.0, "Free Trial", "https://1password.com", "Password manager and secure vault for teams."),
    ("Bitwarden", "Security", 3.0, 0.0, "Free Trial", "https://bitwarden.com", "Open-source password manager with end-to-end encryption."),
    ("NordVPN", "Security", 11.99, 3.99, "Annual Discount", "https://nordvpn.com", "Fast, secure VPN with 5500+ servers in 60 countries."),

    # Finance
    ("Lemon Squeezy", "Finance", 0.0, 0.0, "Free Trial", "https://lemonsqueezy.com", "Merchant of record for SaaS — handles tax, billing, payouts."),
    ("Paddle", "Finance", 0.0, 0.0, "Free Trial", "https://paddle.com", "Subscription billing and revenue management for B2B SaaS."),
    ("Invoice Ninja", "Finance", 14.0, 0.0, "Free Trial", "https://invoiceninja.com", "Open-source invoicing, billing, and time-tracking."),
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
