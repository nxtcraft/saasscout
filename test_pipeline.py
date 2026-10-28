"""Unit and integration tests for pipeline logic and FastAPI endpoints."""

import json
import pytest
from fastapi.testclient import TestClient

from pipeline import (
    _discount, _classify, _deal_id, _affiliate_url,
    _build_seed_deals, _deduplicate, AFFILIATE_TAG, SEED_CATALOGUE,
)
from main import app, DATA_FILE

client = TestClient(app)


# ---------------------------------------------------------------------------
# pipeline — discount logic
# ---------------------------------------------------------------------------

def test_discount_normal():
    assert _discount(100.0, 60.0) == 40.0

def test_discount_zero_original():
    assert _discount(0.0, 10.0) == 0.0

def test_discount_deal_higher():
    assert _discount(50.0, 80.0) == 0.0

def test_discount_full():
    assert _discount(200.0, 0.0) == 100.0

def test_discount_rounding():
    assert _discount(99.0, 59.0) == round((99 - 59) / 99 * 100, 1)


# ---------------------------------------------------------------------------
# pipeline — category classifier
# ---------------------------------------------------------------------------

def test_classify_ai():
    assert _classify("GPT-based automation chatbot") == "AI"

def test_classify_marketing():
    assert _classify("Email marketing and CRM platform") == "Marketing"

def test_classify_devtools():
    assert _classify("Cloud deployment API tool") == "DevTools"

def test_classify_analytics():
    assert _classify("Dashboard analytics reporting insights") == "Analytics"

def test_classify_design():
    assert _classify("UI/UX design and prototype tool") == "Design"

def test_classify_security():
    assert _classify("VPN and password security manager") == "Security"

def test_classify_fallback():
    assert _classify("xyzzy totally unknown widget") == "Other"


# ---------------------------------------------------------------------------
# pipeline — deal ID and affiliate URL
# ---------------------------------------------------------------------------

def test_deal_id_deterministic():
    assert _deal_id("Notion", "seed") == _deal_id("Notion", "seed")

def test_deal_id_unique_source():
    assert _deal_id("Notion", "seed") != _deal_id("Notion", "appsumo")

def test_affiliate_url_no_query():
    url = _affiliate_url("https://example.com/product")
    assert f"ref={AFFILIATE_TAG}" in url
    assert url.startswith("https://example.com/product")

def test_affiliate_url_existing_query():
    url = _affiliate_url("https://example.com/product?plan=pro")
    assert f"ref={AFFILIATE_TAG}" in url
    assert url.count("?") == 1

def test_affiliate_url_empty():
    assert _affiliate_url("") == ""


# ---------------------------------------------------------------------------
# pipeline — seed catalogue
# ---------------------------------------------------------------------------

def test_seed_deals_count():
    assert len(_build_seed_deals()) == len(SEED_CATALOGUE)

def test_seed_deals_structure():
    for d in _build_seed_deals():
        for key in ("id", "name", "category", "deal_price", "original_price",
                    "discount_percent", "affiliate_url", "deal_type", "discovered_at", "source"):
            assert key in d, f"Missing key: {key}"

def test_seed_deals_discount_correct():
    for d in _build_seed_deals():
        if d["original_price"] > 0:
            expected = round((d["original_price"] - d["deal_price"]) / d["original_price"] * 100, 1)
            assert d["discount_percent"] == max(0.0, expected)

def test_seed_no_duplicate_ids():
    deals = _build_seed_deals()
    ids = [d["id"] for d in deals]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# pipeline — deduplication
# ---------------------------------------------------------------------------

def test_deduplicate_removes_dupes():
    d = {"id": "abc", "name": "X"}
    result = _deduplicate([d, d, d])
    assert len(result) == 1

def test_deduplicate_preserves_unique():
    a = {"id": "aaa", "name": "A"}
    b = {"id": "bbb", "name": "B"}
    assert len(_deduplicate([a, b])) == 2


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def seed_data_file(tmp_path, monkeypatch):
    import main
    tmp_file = tmp_path / "latest_deals.json"
    tmp_file.write_text(json.dumps(_build_seed_deals()))
    monkeypatch.setattr(main, "DATA_FILE", tmp_file)


def test_health_200():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total_deals"] >= len(SEED_CATALOGUE)


def test_deals_200():
    resp = client.get("/v1/deals")
    assert resp.status_code == 200
    data = resp.json()
    assert "deals" in data
    assert "total" in data
    assert data["total"] >= len(SEED_CATALOGUE)


def test_deals_sorted_by_discount():
    resp = client.get("/v1/deals?per_page=100")
    deals = resp.json()["deals"]
    discounts = [d["discount_percent"] for d in deals]
    assert discounts == sorted(discounts, reverse=True)


def test_deals_pagination():
    page1 = client.get("/v1/deals?page=1&per_page=5").json()["deals"]
    page2 = client.get("/v1/deals?page=2&per_page=5").json()["deals"]
    assert len(page1) == 5
    assert page1[0]["id"] != page2[0]["id"]


def test_deals_filter_category():
    resp = client.get("/v1/deals?category=AI")
    for d in resp.json()["deals"]:
        assert d["category"] == "AI"


def test_deals_filter_max_price():
    resp = client.get("/v1/deals?max_price=0")
    for d in resp.json()["deals"]:
        assert d["deal_price"] <= 0


def test_deals_filter_min_discount():
    resp = client.get("/v1/deals?min_discount=30")
    for d in resp.json()["deals"]:
        assert d["discount_percent"] >= 30


def test_deals_filter_deal_type_ltd():
    resp = client.get("/v1/deals?deal_type=ltd")
    for d in resp.json()["deals"]:
        assert d["deal_type"] == "Lifetime Deal"


def test_top_deals():
    resp = client.get("/v1/deals/top?n=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


def test_search_endpoint():
    resp = client.get("/v1/search?q=email")
    assert resp.status_code == 200
    results = resp.json()
    assert all("email" in d["name"].lower() or "email" in d["description"].lower() for d in results)


def test_categories_200():
    resp = client.get("/v1/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    names = [c["name"] for c in data["categories"]]
    assert "AI" in names
    assert "Marketing" in names


def test_deal_by_id():
    all_deals = client.get("/v1/deals?per_page=1").json()["deals"]
    deal_id = all_deals[0]["id"]
    resp = client.get(f"/v1/deals/{deal_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == deal_id


def test_deal_not_found():
    assert client.get("/v1/deals/nonexistent-000").status_code == 404
