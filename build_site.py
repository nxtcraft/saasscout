"""Build SEO-optimized static site for SaaSScout GitHub Pages."""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path("data/latest_deals.json")
DIST_DIR = Path("dist")
RAPIDAPI_URL = "https://rapidapi.com/PradeepKumarKesharwani/api/saasscout"
GITHUB_URL = "https://github.com/nxtcraft/saasscout"


def load_deals():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_index(deals):
    updated = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    ltd_count = sum(1 for d in deals if d.get("deal_type") == "Lifetime Deal")
    avg_disc = int(statistics.mean(d["discount_percent"] for d in deals)) if deals else 0
    cats = sorted({d["category"] for d in deals})

    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Best SaaS Deals & Lifetime Offers",
        "description": f"Curated list of {len(deals)} SaaS deals including lifetime deals, free trials, and discounts.",
        "url": "https://nxtcraft.github.io/saasscout",
        "numberOfItems": len(deals),
    }

    cat_buttons = "".join(
        f'<button class="cat-btn" onclick="filterCat(\'{c}\')">{c}</button>'
        for c in cats
    )

    cards = ""
    for d in deals:
        disc = int(d["discount_percent"])
        badge_cls = "badge-ltd" if d["deal_type"] == "Lifetime Deal" else "badge-disc" if d["deal_type"] == "Annual Discount" else "badge-trial"
        price_html = (
            f'<span class="orig">${d["original_price"]:.0f}</span> <span class="deal-price">${d["deal_price"]:.0f}</span>'
            if d["deal_price"] > 0
            else '<span class="deal-price free">FREE</span>'
        )
        cards += f"""
<article class="card" data-cat="{d['category']}" data-type="{d['deal_type']}" data-disc="{disc}">
  <div class="card-head">
    <div>
      <h2 class="deal-name">{d['name']}</h2>
      <span class="cat-tag">{d['category']}</span>
    </div>
    <span class="badge {badge_cls}">{d['deal_type']}</span>
  </div>
  <p class="deal-desc">{d['description']}</p>
  <div class="card-foot">
    <div class="pricing">{price_html} <span class="disc-pct">-{disc}%</span></div>
    <a class="cta-btn" href="{d['affiliate_url']}" target="_blank" rel="noopener sponsored">Get Deal →</a>
  </div>
</article>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="description" content="Browse {len(deals)} hand-picked SaaS deals: lifetime offers, free trials, and big discounts on AI, DevTools, Marketing tools and more. Updated daily."/>
<meta name="keywords" content="saas deals, lifetime deals, appsumo deals, saas discounts, free saas tools, ai tools deals, devtools lifetime deal"/>
<meta property="og:title" content="SaaSScout — Best SaaS Lifetime Deals & Discounts"/>
<meta property="og:description" content="{len(deals)} SaaS deals tracked. Find lifetime deals, free trials, and discounts on the best tools."/>
<meta property="og:type" content="website"/>
<title>SaaSScout — Best SaaS Lifetime Deals &amp; Discounts</title>
<script type="application/ld+json">{json.dumps(schema)}</script>
<style>
:root{{--bg:#0d1117;--bg2:#161b22;--card:#1c2128;--border:#30363d;--fg:#e6edf3;--fg2:#8b949e;--fg3:#484f58;--accent:#58a6ff;--green:#3fb950;--yellow:#d29922;--purple:#bc8cff;color-scheme:dark}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--fg);line-height:1.6}}
header{{background:linear-gradient(160deg,#0d2137 0%,#0d1117 60%);padding:56px 20px 44px;text-align:center;border-bottom:1px solid var(--border)}}
.live{{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--green);font-weight:600;letter-spacing:.6px;text-transform:uppercase;margin-bottom:16px}}
.dot{{width:7px;height:7px;background:var(--green);border-radius:50%;animation:blink 2s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
h1{{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:700;color:#fff;margin-bottom:10px}}
h1 span{{color:var(--accent)}}
.sub{{color:var(--fg2);font-size:1rem;max-width:500px;margin:0 auto 28px}}
.cta-bar{{background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.2);border-radius:8px;padding:12px 18px;max-width:640px;margin:0 auto;font-size:13px;color:var(--fg2)}}
.cta-bar a{{color:var(--accent);font-weight:600}}
.stats{{display:flex;justify-content:center;background:var(--bg2);border-bottom:1px solid var(--border)}}
.stat{{text-align:center;padding:18px 28px;border-right:1px solid var(--border);flex:1;max-width:160px}}
.stat:last-child{{border-right:none}}
.sn{{font-size:1.5rem;font-weight:700;color:var(--accent)}}
.sl{{font-size:11px;color:var(--fg3);text-transform:uppercase;letter-spacing:.4px;margin-top:2px}}
.controls{{max-width:1040px;margin:28px auto;padding:0 16px;display:flex;flex-direction:column;gap:12px}}
.row{{display:flex;gap:10px;flex-wrap:wrap}}
#search{{flex:1;min-width:180px;background:var(--card);border:1px solid var(--border);border-radius:7px;padding:9px 13px;color:var(--fg);font-size:13px;outline:none}}
#search:focus{{border-color:var(--accent)}}
select{{background:var(--card);border:1px solid var(--border);border-radius:7px;padding:9px 13px;color:var(--fg);font-size:13px;cursor:pointer;outline:none}}
.cat-filters{{display:flex;flex-wrap:wrap;gap:7px}}
.cat-btn{{background:var(--bg2);border:1px solid var(--border);color:var(--fg2);padding:4px 11px;border-radius:20px;font-size:12px;cursor:pointer;transition:.12s}}
.cat-btn:hover,.cat-btn.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.count{{font-size:12px;color:var(--fg3)}}
.grid{{max-width:1040px;margin:0 auto;padding:0 16px 56px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;display:flex;flex-direction:column;gap:12px;transition:border-color .15s}}
.card:hover{{border-color:var(--accent)}}
.card.hidden{{display:none}}
.card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}}
.deal-name{{font-size:14px;font-weight:600;color:var(--fg);margin-bottom:4px}}
.cat-tag{{font-size:11px;color:var(--fg3);background:var(--bg2);padding:2px 7px;border-radius:3px}}
.badge{{font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0}}
.badge-ltd{{background:rgba(188,140,255,.15);color:var(--purple);border:1px solid rgba(188,140,255,.25)}}
.badge-disc{{background:rgba(88,166,255,.12);color:var(--accent);border:1px solid rgba(88,166,255,.2)}}
.badge-trial{{background:rgba(63,185,80,.12);color:var(--green);border:1px solid rgba(63,185,80,.2)}}
.deal-desc{{font-size:12px;color:var(--fg2);flex:1}}
.card-foot{{display:flex;justify-content:space-between;align-items:center;gap:10px}}
.pricing{{font-size:13px}}
.orig{{color:var(--fg3);text-decoration:line-through;margin-right:6px}}
.deal-price{{font-weight:700;color:var(--green)}}
.deal-price.free{{color:var(--accent)}}
.disc-pct{{color:var(--yellow);font-weight:600;font-size:11px;margin-left:4px}}
.cta-btn{{background:var(--accent);color:#fff;padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;white-space:nowrap;transition:opacity .15s}}
.cta-btn:hover{{opacity:.85}}
.none{{display:none;text-align:center;padding:48px;color:var(--fg3)}}
.none.show{{display:block}}
footer{{text-align:center;padding:28px;border-top:1px solid var(--border);color:var(--fg3);font-size:12px}}
footer a{{color:var(--accent)}}
@media(max-width:560px){{.stats{{flex-wrap:wrap}}.stat{{min-width:50%;border-right:none;border-bottom:1px solid var(--border)}}.card-foot{{flex-direction:column;align-items:flex-start}}}}
</style>
</head>
<body>
<header>
  <div class="live"><span class="dot"></span>Updated {updated}</div>
  <h1>SaaSScout — <span>Best SaaS Deals</span></h1>
  <p class="sub">Lifetime deals, free trials, and deep discounts on the tools developers and founders actually use.</p>
  <div class="cta-bar">Need programmatic access? <a href="{RAPIDAPI_URL}" target="_blank">Subscribe on RapidAPI</a> — filter by category, discount %, deal type.</div>
</header>
<div class="stats">
  <div class="stat"><div class="sn">{len(deals)}</div><div class="sl">Active Deals</div></div>
  <div class="stat"><div class="sn">{ltd_count}</div><div class="sl">Lifetime Deals</div></div>
  <div class="stat"><div class="sn">{avg_disc}%</div><div class="sl">Avg Discount</div></div>
  <div class="stat"><div class="sn">{len(cats)}</div><div class="sl">Categories</div></div>
</div>
<div class="controls">
  <div class="row">
    <input id="search" type="search" placeholder="Search deals, tools, categories..." oninput="filter()"/>
    <select id="type-sel" onchange="filter()">
      <option value="">All Types</option>
      <option>Lifetime Deal</option>
      <option>Annual Discount</option>
      <option>Free Trial</option>
    </select>
    <select id="disc-sel" onchange="filter()">
      <option value="0">Any Discount</option>
      <option value="50">50%+</option>
      <option value="70">70%+</option>
      <option value="85">85%+</option>
      <option value="90">90%+</option>
    </select>
  </div>
  <div class="cat-filters">
    <span style="font-size:11px;color:var(--fg3);align-self:center;margin-right:2px">Category:</span>
    {cat_buttons}
    <button class="cat-btn" id="clear-btn" onclick="clearAll()" style="display:none">✕ Clear</button>
  </div>
  <div class="count" id="count">{len(deals)} deals shown</div>
</div>
<div class="grid" id="grid">{cards}</div>
<div class="none" id="none">No deals match. <a href="#" onclick="clearAll();return false">Clear filters</a></div>
<footer><a href="{RAPIDAPI_URL}" target="_blank">API on RapidAPI</a> · <a href="{GITHUB_URL}" target="_blank">GitHub</a> · Updated daily</footer>
<script>
let activeCat=null;
function filter(){{
  const q=document.getElementById('search').value.toLowerCase();
  const typ=document.getElementById('type-sel').value;
  const minD=parseInt(document.getElementById('disc-sel').value)||0;
  let n=0;
  document.querySelectorAll('.card').forEach(c=>{{
    const ok=(!q||c.innerText.toLowerCase().includes(q))&&
              (!typ||c.dataset.type===typ)&&
              (parseInt(c.dataset.disc)>=minD)&&
              (!activeCat||c.dataset.cat===activeCat);
    c.classList.toggle('hidden',!ok);
    if(ok)n++;
  }});
  document.getElementById('count').textContent=n+' deals shown';
  document.getElementById('none').classList.toggle('show',n===0);
  document.getElementById('clear-btn').style.display=(q||typ||minD||activeCat)?'inline-block':'none';
}}
function filterCat(c){{
  activeCat=activeCat===c?null:c;
  document.querySelectorAll('.cat-btn').forEach(b=>b.classList.toggle('active',b.textContent===c&&activeCat));
  filter();
}}
function clearAll(){{
  activeCat=null;
  document.getElementById('search').value='';
  document.getElementById('type-sel').value='';
  document.getElementById('disc-sel').value='0';
  document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
  filter();
}}
</script>
</body></html>"""


def main():
    print("Loading deals...")
    deals = load_deals()
    print(f"Loaded {len(deals)} deals.")
    DIST_DIR.mkdir(exist_ok=True)
    print("Building index.html...")
    (DIST_DIR / "index.html").write_text(build_index(deals), encoding="utf-8")
    (DIST_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://nxtcraft.github.io/saasscout/sitemap.xml\n"
    )
    (DIST_DIR / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>https://nxtcraft.github.io/saasscout/</loc><lastmod>{datetime.now(timezone.utc).strftime("%Y-%m-%d")}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        "</urlset>\n"
    )
    (DIST_DIR / "404.html").write_text(
        '<!DOCTYPE html><html><head><meta charset="UTF-8"/><title>Not Found – SaaSScout</title>'
        '<style>body{font-family:sans-serif;background:#0d1117;color:#e6edf3;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center}</style></head>'
        '<body><div><h1 style="color:#58a6ff;font-size:3rem">404</h1><p style="color:#8b949e;margin:12px 0 24px">Page not found.</p>'
        '<a href="/saasscout/" style="background:#58a6ff;color:#fff;padding:10px 22px;border-radius:7px;text-decoration:none;font-weight:600">Back to Deals →</a></div></body></html>',
        encoding="utf-8",
    )
    print(f"Done. {len(list(DIST_DIR.iterdir()))} files in dist/")


if __name__ == "__main__":
    main()
