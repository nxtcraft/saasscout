"""Unit and integration tests for pipeline logic and FastAPI endpoints."""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from pipeline import _discount, _classify, _deal_id, _affiliate_url, _build_seed_deals, AFFILIATE_TAG
from main import app, DATA_FILE

client = TestClient(app)


# ---------------------------------------------------------------------------
# pipeline unit tests
# ---------------------------------------------------------------------------

def test_discount_normal():
    assert _discount(100.0, 60.0) == 40.0


def test_discount_zero_original():
    assert _discount(0.0, 10.0) == 0.0


def test_discount_deal_higher_than_original():
    assert _discount(50.0, 80.0) == 0.0


def test_discount_full():
    assert _discount(200.0, 0.0) == 100.0


def test_classify_ai():
    assert _classify("GPT-based automation chatbot") == "AI"


def test_classify_marketing():
    assert _classify("Email marketing and CRM platform") == "Marketing"


def test_classify_devtools():
    assert _classify("Cloud deployment API tool") == "DevTools"


def test_classify_analytics():
    assert _classify("Dashboard analytics reporting insights") == "Analytics"


def test_classify_fallback():
    assert _classify("Generic unnamed tool") == "Other"


def test_deal_id_deterministic():
    assert _deal_id("Notion", "seed") == _deal_id("Notion", "seed")


def test_deal_id_unique_per_source():
    assert _deal_id("Notion", "seed") != _deal_id("Notion", "appsumo")


def test_affiliate_url_appends_tag():
    url = _affiliate_url("https://example.com/product")
    assert f"ref={AFFILIATE_TAG}" in url


def test_affiliate_url_existing_query():
    url = _affiliate_url("https://example.com/product?plan=pro")
    assert f"ref={AFFILIATE_TAG}" in url
    assert url.count("?") == 1


def test_affiliate_url_empty():
    assert _affiliate_url("") == ""


def test_seed_deals_structure():
    deals = _build_seed_deals()
    assert len(deals) > 0
    for d in deals:
        assert "id" in d
        assert "name" in d
        assert "category" in d
        assert "deal_price" in d
        assert "original_price" in d
        assert "discount_percent" in d
        assert "affiliate_url" in d
        assert "deal_type" in d
        assert "discovered_at" in d


def test_seed_deals_discount_calculated():
    deals = _build_seed_deals()
    for d in deals:
        expected = max(0.0, round((d["original_price"] - d["deal_price"]) / d["original_price"] * 100, 1)) if d["original_price"] > 0 else 0.0
        assert d["discount_percent"] == expected


# ---------------------------------------------------------------------------
# API integration tests (requires data file)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def seed_data_file(tmp_path, monkeypatch):
    """Write seed deals into a temp data file and patch DATA_FILE."""
    from pipeline import _build_seed_deals
    import main

    tmp_file = tmp_path / "latest_deals.json"
    tmp_file.write_text(json.dumps(_build_seed_deals()))
    monkeypatch.setattr(main, "DATA_FILE", tmp_file)
    yield


def test_health_200():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total_deals"] > 0


def test_deals_200():
    resp = client.get("/v1/deals")
    assert resp.status_code == 200
    deals = resp.json()
    assert isinstance(deals, list)
    assert len(deals) > 0


def test_deals_sorted_by_discount():
    resp = client.get("/v1/deals")
    deals = resp.json()
    discounts = [d["discount_percent"] for d in deals]
    assert discounts == sorted(discounts, reverse=True)


def test_deals_filter_category():
    resp = client.get("/v1/deals?category=AI")
    assert resp.status_code == 200
    for d in resp.json():
        assert d["category"] == "AI"


def test_deals_filter_max_price():
    resp = client.get("/v1/deals?max_price=0")
    assert resp.status_code == 200
    for d in resp.json():
        assert d["deal_price"] <= 0


def test_deals_filter_deal_type_ltd():
    resp = client.get("/v1/deals?deal_type=ltd")
    assert resp.status_code == 200
    for d in resp.json():
        assert d["deal_type"] == "Lifetime Deal"


def test_deals_limit():
    resp = client.get("/v1/deals?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


def test_categories_200():
    resp = client.get("/v1/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert isinstance(data["categories"], list)


def test_deal_by_id():
    all_deals = client.get("/v1/deals").json()
    if not all_deals:
        pytest.skip("No deals available")
    first_id = all_deals[0]["id"]
    resp = client.get(f"/v1/deals/{first_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == first_id


def test_deal_by_id_not_found():
    resp = client.get("/v1/deals/nonexistent-id")
    assert resp.status_code == 404
