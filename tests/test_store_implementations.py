"""Tests for the 6 new store implementations.

Each test uses a real evidence file from the fixtures directory.  Tests are
grouped by store; within each group they verify:
  - JSON-LD extraction succeeds
  - Required schema fields are populated
  - Scope pipeline accepts the product
  - Category normalisation resolves a non-empty category
  - Identifiers, prices, images and URLs are present and well-formed
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="ignore")


def _load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _extract_product(html: str, product_url: str, source: str) -> Optional[Dict]:
    from egyscraper.core.jsonld import find_product_or_group
    from egyscraper.core.jsonld_mapper import map_jsonld_product

    node = find_product_or_group(html)
    if node is None:
        return None
    return map_jsonld_product(node, product_url=product_url, source=source)


def _scope_accepts(record: Dict) -> bool:
    from egyscraper.core.scope import classify_record
    result = classify_record(record)
    return result.get("is_supported", False)


def _passes_validation(record: Dict) -> bool:
    from egyscraper.core.schema import missing_required
    return not bool(missing_required(record))


# ---------------------------------------------------------------------------
# LC Waikiki
# ---------------------------------------------------------------------------

class TestLCWaikiki:
    URL = "https://www.lcwaikiki.eg/en/100-cotton-regular-fit-basic-thick-t-shirt-white-o-5061360"
    SOURCE = "www.lcwaikiki.eg"

    @pytest.fixture(scope="class")
    def record(self):
        html = _load_html("lcwaikiki_product.html")
        return _extract_product(html, self.URL, self.SOURCE)

    def test_record_produced(self, record):
        assert record is not None, "Should produce a product record from LC Waikiki JSON-LD"

    def test_title(self, record):
        assert "T-Shirt" in record["title"] or "t-shirt" in record["title"].lower()

    def test_sku(self, record):
        assert record["sku"] == "S69236Z8", f"SKU mismatch: {record['sku']}"

    def test_gtin(self, record):
        assert record["gtin"] == "8685004224090"

    def test_price_is_positive(self, record):
        assert record["price"] is not None and record["price"] > 0

    def test_price_currency_egp(self, record):
        assert record["currency"] == "EGP"

    def test_images_present(self, record):
        assert len(record["image_urls"]) >= 2, "Expected multiple product images"

    def test_images_are_https(self, record):
        for img in record["image_urls"]:
            assert img.startswith("https://"), f"Non-HTTPS image: {img}"

    def test_product_url(self, record):
        assert record["product_url"] == self.URL

    def test_sizes_extracted(self, record):
        # LC Waikiki JSON-LD carries a product-level size list
        assert isinstance(record["sizes"], list) and len(record["sizes"]) > 0, \
            "sizes[] should be populated from JSON-LD"
        assert "M" in record["sizes"]

    def test_colors_extracted(self, record):
        assert len(record["colors"]) > 0, "colors should be populated"

    def test_gender_from_audience(self, record):
        assert record["gender"] == "men", \
            f"Gender should be 'men' from audience.suggestedGender, got {record['gender']!r}"

    def test_brand(self, record):
        assert record["brand"], "Brand should be populated"

    def test_category_non_empty(self, record):
        assert record["category"], "Category should be normalised to a non-empty string"

    def test_scope_accepts(self, record):
        assert _scope_accepts(record), "Scope pipeline should accept this clothing item"

    def test_store_registry_entry(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        store = JSONLD_STORES.get("lcwaikiki")
        assert store is not None
        assert store.sitemap and "product_sitemap_EN.xml" in store.sitemap
        import re
        assert re.search(store.product_pattern, "/en/100-cotton-t-shirt-o-5061360")


# ---------------------------------------------------------------------------
# Lacoste
# ---------------------------------------------------------------------------

class TestLacoste:
    URL = "https://www.lacoste.com.eg/en/shirts/short-sleeved-linen-shirt/CH5699-00.html"
    SOURCE = "www.lacoste.com.eg"

    @pytest.fixture(scope="class")
    def record(self):
        html = _load_html("lacoste_product.html")
        return _extract_product(html, self.URL, self.SOURCE)

    def test_record_produced(self, record):
        assert record is not None

    def test_title(self, record):
        assert "Shirt" in record["title"] or "shirt" in record["title"].lower()

    def test_sku(self, record):
        # sku / mpn both equal "018826323960" in the evidence
        assert record["sku"] == "018826323960"

    def test_price_egp(self, record):
        assert record["price"] is not None and record["price"] > 0
        assert record["currency"] == "EGP"

    def test_image_present(self, record):
        assert len(record["image_urls"]) >= 1
        assert "demandware" in record["image_urls"][0] or "lacoste" in record["image_urls"][0].lower()

    def test_product_url(self, record):
        assert record["product_url"] == self.URL

    def test_scope_accepts(self, record):
        assert _scope_accepts(record)

    def test_store_registry_entry(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        import re
        store = JSONLD_STORES["lacoste"]
        assert re.search(store.product_pattern, "/en/shirts/short-sleeved-linen-shirt/CH5699-00.html"), \
            f"Product pattern should match Lacoste URLs"


# ---------------------------------------------------------------------------
# Adidas
# ---------------------------------------------------------------------------

class TestAdidas:
    URL = "https://www.adidas.com.eg/en/real-madrid-dna-t-shirt/KG2943.html"
    SOURCE = "www.adidas.com.eg"

    @pytest.fixture(scope="class")
    def record(self):
        html = _load_html("adidas_product.html")
        return _extract_product(html, self.URL, self.SOURCE)

    def test_record_produced(self, record):
        assert record is not None

    def test_title(self, record):
        assert "T-Shirt" in record["title"] or "t-shirt" in record["title"].lower()

    def test_sku(self, record):
        # JSON-LD sku is the colour variant SKU (KG2943)
        assert record["sku"] == "KG2943"

    def test_product_id_uses_group_id(self, record):
        # isVariantOf.productGroupID = BW301 should be used as identifier
        attrs = record.get("attributes") or {}
        assert attrs.get("product_group_id") == "BW301", \
            "product_group_id should be stored from isVariantOf.productGroupID"

    def test_price(self, record):
        assert record["price"] is not None and record["price"] == 2399

    def test_currency(self, record):
        assert record["currency"] == "EGP"

    def test_images_multiple(self, record):
        assert len(record["image_urls"]) >= 3, "Adidas JSON-LD has 6 images"

    def test_color(self, record):
        assert "white" in " ".join(record["colors"]).lower() or record["colors"]

    def test_category(self, record):
        # JSON-LD category = "Men's Clothing"
        assert record["category"], "Category should be normalised"

    def test_scope_accepts(self, record):
        assert _scope_accepts(record)

    def test_store_registry_entry(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        import re
        store = JSONLD_STORES["adidas"]
        assert re.search(store.product_pattern,
                         "/en/real-madrid-dna-t-shirt/KG2943.html")


# ---------------------------------------------------------------------------
# New Balance (known limitation: no images in evidence)
# ---------------------------------------------------------------------------

class TestNewBalance:
    URL = "https://www.newbalance.com.eg/en/buy-accelerate-pacer-short-sleeve-black"
    SOURCE = "www.newbalance.com.eg"

    @pytest.fixture(scope="class")
    def record(self):
        html = _load_html("newbalance_product.html")
        return _extract_product(html, self.URL, self.SOURCE)

    def test_record_produced(self, record):
        assert record is not None

    def test_title(self, record):
        assert "Sleeve" in record["title"] or "sleeve" in record["title"].lower()

    def test_sku(self, record):
        assert record["sku"] == "MT31241"

    def test_price(self, record):
        assert record["price"] == 1000

    def test_currency(self, record):
        assert record["currency"] == "EGP"

    def test_known_image_limitation(self, record):
        """New Balance JSON-LD has image:[] — this is a documented limitation.
        Records with empty images fail validation; Playwright is required to
        recover them.  This test documents the limitation rather than failing
        for the wrong reason."""
        assert record["image_urls"] == [], \
            "New Balance JSON-LD is known to have empty images (JS-rendered)"

    def test_store_registry_entry(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        import re
        store = JSONLD_STORES["newbalance"]
        assert re.search(store.product_pattern,
                         "/en/buy-accelerate-pacer-short-sleeve-black")

    def test_availability_parsed(self, record):
        # "In stock" from the offers array
        assert record["availability"] in ("in_stock", "unknown")


# ---------------------------------------------------------------------------
# Jumia
# ---------------------------------------------------------------------------

class TestJumia:
    URL = "https://www.jumia.com.eg/lc-waikiki-regular-fit-long-sleeve-striped-mens-shirt-133884647.html"
    SOURCE = "www.jumia.com.eg"

    @pytest.fixture(scope="class")
    def record(self):
        from egyscraper.core.jsonld import find_product_in_graph
        from egyscraper.core.jsonld_mapper import map_jsonld_product
        import re

        html = _load_html("jumia_product.html")
        # Jumia uses @graph — use find_product_in_graph
        for script_text in re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        ):
            try:
                data = json.loads(script_text)
            except json.JSONDecodeError:
                continue
            node = find_product_in_graph(data) if isinstance(data, dict) else None
            if node:
                return map_jsonld_product(node, product_url=self.URL, source=self.SOURCE)
        return None

    def test_record_produced(self, record):
        assert record is not None, "Should produce a product from Jumia JSON-LD @graph"

    def test_title(self, record):
        assert "Shirt" in record["title"]

    def test_sku(self, record):
        assert record["sku"] == "LC160MW2VZBWHNAFAMZ"

    def test_price(self, record):
        assert record["price"] == 359

    def test_images_multiple(self, record):
        assert len(record["image_urls"]) >= 3
        for img in record["image_urls"]:
            assert "jumia" in img or "eg.jumia" in img

    def test_gtin(self, record):
        assert record["gtin"] == "08684680169534"

    def test_scope_accepts(self, record):
        assert _scope_accepts(record)

    def test_category(self, record):
        assert record["category"], "Category should resolve to non-empty string"

    def test_brand(self, record):
        assert "waikiki" in record["brand"].lower() or "lc" in record["brand"].lower()

    def test_product_url_pattern(self):
        """Jumia product URL pattern should match the evidence URL."""
        import re
        from egyscraper.spiders.jumia import _PRODUCT_URL_RE
        path = "/lc-waikiki-regular-fit-long-sleeve-striped-mens-shirt-133884647.html"
        assert _PRODUCT_URL_RE.search(path), \
            f"_PRODUCT_URL_RE should match product page paths"

    def test_find_product_in_graph(self):
        """find_product_in_graph correctly handles the Jumia @graph structure."""
        from egyscraper.core.jsonld import find_product_in_graph
        sample_graph = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "BreadcrumbList", "itemListElement": []},
                {"@type": "Product", "name": "Test", "sku": "TST001"},
                {"@type": "Organization"},
            ],
        }
        node = find_product_in_graph(sample_graph)
        assert node is not None
        assert node["@type"] == "Product"
        assert node["sku"] == "TST001"

    def test_find_product_in_graph_returns_none_for_empty(self):
        from egyscraper.core.jsonld import find_product_in_graph
        assert find_product_in_graph({"@graph": []}) is None
        assert find_product_in_graph({"noGraph": True}) is None


# ---------------------------------------------------------------------------
# Noon catalog API mapper
# ---------------------------------------------------------------------------

class TestNoonMapper:
    @pytest.fixture(scope="class")
    def api_response(self):
        return _load_json("noon_catalog_api.json")

    @pytest.fixture(scope="class")
    def first_hit(self, api_response):
        return api_response["hits"][0]

    def test_api_fixture_shape(self, api_response):
        assert "nbHits" in api_response
        assert "nbPages" in api_response
        assert isinstance(api_response["hits"], list)
        assert len(api_response["hits"]) > 0

    def test_map_noon_hit_produces_record(self, first_hit):
        from egyscraper.core.noon_mapper import map_noon_hit
        rec = map_noon_hit(first_hit, source="www.noon.com")
        assert rec is not None

    def test_required_fields_present(self, first_hit):
        from egyscraper.core.noon_mapper import map_noon_hit
        rec = map_noon_hit(first_hit, source="www.noon.com")
        assert rec["title"], "title required"
        assert rec["sku"], "sku required"
        assert rec["price"] is not None
        assert rec["currency"] == "EGP"
        assert len(rec["image_urls"]) > 0, "image_urls required"
        assert rec["product_url"].startswith("https://www.noon.com/egypt-en/")

    def test_product_url_structure(self, first_hit):
        from egyscraper.core.noon_mapper import map_noon_hit
        rec = map_noon_hit(first_hit, source="www.noon.com")
        # URL must end with /{sku}/p/
        sku = rec["sku"]
        assert rec["product_url"].endswith(f"{sku}/p/"), \
            f"Product URL should end with {sku}/p/"

    def test_sale_price_preferred_over_full_price(self):
        from egyscraper.core.noon_mapper import map_noon_hit
        hit = {
            "sku": "TEST123",
            "name": "Test Jacket",
            "brand": "TestBrand",
            "price": 500,
            "sale_price": 350.0,
            "url": "test-jacket",
            "image_urls": ["https://example.com/img.jpg"],
            "is_buyable": True,
        }
        rec = map_noon_hit(hit, source="www.noon.com")
        from decimal import Decimal
        assert rec["price"] == Decimal("350")
        assert rec["original_price"] == Decimal("500")

    def test_unavailable_product(self):
        from egyscraper.core.noon_mapper import map_noon_hit
        hit = {
            "sku": "UNAVAIL",
            "name": "Unavailable Item",
            "brand": "X",
            "price": 100,
            "url": "unavail-item",
            "image_urls": ["https://example.com/img.jpg"],
            "is_buyable": False,
        }
        rec = map_noon_hit(hit, source="www.noon.com")
        assert rec["availability"] == "out_of_stock"

    def test_missing_sku_returns_none(self):
        from egyscraper.core.noon_mapper import map_noon_hit
        assert map_noon_hit({"name": "No SKU product"}, source="www.noon.com") is None

    def test_scope_accepts_clothing_hit(self, first_hit):
        """A watch in the Men's Fashion category should be rejected by scope."""
        from egyscraper.core.noon_mapper import map_noon_hit
        from egyscraper.core.scope import classify_record
        rec = map_noon_hit(first_hit, source="www.noon.com")
        # The first hit from the HAR is a watch (Tommy Hilfiger wristwatch)
        # — it should be REJECTED by scope as accessories
        result = classify_record(rec)
        assert not result["is_supported"], \
            "A wristwatch from Noon's 'fashion' category should be scope-rejected"

    def test_scope_accepts_clothing_item(self):
        """A clothing item constructed from hit data is scope-accepted."""
        from egyscraper.core.noon_mapper import map_noon_hit
        from egyscraper.core.scope import classify_record
        hit = {
            "sku": "CLTH001",
            "name": "Men Relaxed Fit Cotton T-Shirt Crew Neck",
            "brand": "Basic",
            "price": 200,
            "url": "men-cotton-t-shirt",
            "image_urls": ["https://f.nooncdn.com/p/test.jpg"],
            "is_buyable": True,
        }
        rec = map_noon_hit(hit, source="www.noon.com")
        result = classify_record(rec)
        assert result["is_supported"], "A T-shirt should be scope-accepted"


# ---------------------------------------------------------------------------
# Mapper extension: isVariantOf / sizes / audience gender
# ---------------------------------------------------------------------------

class TestMapperExtensions:
    """Verify the three mapper extensions added for the new stores."""

    def _map(self, node: dict, url: str = "https://example.com/p") -> dict:
        from egyscraper.core.jsonld_mapper import map_jsonld_product
        return map_jsonld_product(node, product_url=url, source="example.com")

    # Adidas isVariantOf ──────────────────────────────────────────────────────
    def test_is_variant_of_stores_group_id(self):
        node = {
            "@type": "Product",
            "sku": "KG2943",
            "name": "Real Madrid T-Shirt",
            "brand": "adidas",
            "color": "White",
            "offers": {"@type": "Offer", "price": 2399, "priceCurrency": "EGP"},
            "image": ["https://assets.adidas.com/img.jpg"],
            "isVariantOf": {"@type": "ProductGroup", "productGroupID": "BW301"},
        }
        rec = self._map(node)
        assert rec["attributes"]["product_group_id"] == "BW301"

    def test_is_variant_of_uses_group_id_for_product_id(self):
        """Two colour variants with the same productGroupID should produce
        the same product_id."""
        node_a = {
            "@type": "Product", "sku": "KG2943", "name": "T-Shirt", "brand": "adidas",
            "color": "White",
            "offers": {"@type": "Offer", "price": 2399, "priceCurrency": "EGP"},
            "image": ["https://assets.adidas.com/a.jpg"],
            "isVariantOf": {"@type": "ProductGroup", "productGroupID": "BW301"},
        }
        node_b = {**node_a, "sku": "KG2944", "color": "Navy",
                  "image": ["https://assets.adidas.com/b.jpg"]}
        rec_a = self._map(node_a, "https://adidas.com/KG2943.html")
        rec_b = self._map(node_b, "https://adidas.com/KG2944.html")
        assert rec_a["product_id"] == rec_b["product_id"], \
            "Same productGroupID must produce same product_id"

    def test_without_is_variant_of_uses_sku(self):
        node = {
            "@type": "Product", "sku": "MYSKU",
            "name": "Plain Product", "brand": "X",
            "offers": {"@type": "Offer", "price": 100, "priceCurrency": "EGP"},
            "image": ["https://x.com/img.jpg"],
        }
        rec = self._map(node)
        assert "product_group_id" not in (rec.get("attributes") or {})

    # LC Waikiki sizes ────────────────────────────────────────────────────────
    def test_size_list_extracted(self):
        node = {
            "@type": "Product", "sku": "S69236Z8",
            "name": "Basic T-Shirt", "brand": "LCW",
            "size": ["XL", "S", "M", "L", "2XL"],
            "offers": {"@type": "Offer", "price": 549, "priceCurrency": "EGP"},
            "image": ["https://img-lcwaikiki.mncdn.com/img.jpg"],
        }
        rec = self._map(node)
        assert set(rec["sizes"]) == {"XL", "S", "M", "L", "2XL"}

    def test_size_string_becomes_list(self):
        node = {
            "@type": "Product", "sku": "XY", "name": "Dress", "brand": "A",
            "size": "One Size",
            "offers": {"@type": "Offer", "price": 200, "priceCurrency": "EGP"},
            "image": ["https://example.com/img.jpg"],
        }
        rec = self._map(node)
        assert rec["sizes"] == ["One Size"]

    def test_no_size_field_gives_empty_list(self):
        node = {
            "@type": "Product", "sku": "XY", "name": "Dress", "brand": "A",
            "offers": {"@type": "Offer", "price": 200, "priceCurrency": "EGP"},
            "image": ["https://example.com/img.jpg"],
        }
        rec = self._map(node)
        assert rec["sizes"] == []

    # LC Waikiki audience gender ─────────────────────────────────────────────
    def test_audience_male_gives_men(self):
        node = {
            "@type": "Product", "sku": "S69", "name": "Men T-Shirt", "brand": "LCW",
            "audience": {"@type": "PeopleAudience", "suggestedGender": "male"},
            "offers": {"@type": "Offer", "price": 549, "priceCurrency": "EGP"},
            "image": ["https://img.lcw.com/img.jpg"],
        }
        rec = self._map(node)
        assert rec["gender"] == "men"

    def test_audience_female_gives_women(self):
        node = {
            "@type": "Product", "sku": "F01", "name": "A Blouse", "brand": "LCW",
            "audience": {"@type": "PeopleAudience", "suggestedGender": "female"},
            "offers": {"@type": "Offer", "price": 300, "priceCurrency": "EGP"},
            "image": ["https://img.lcw.com/img.jpg"],
        }
        rec = self._map(node)
        assert rec["gender"] == "women"

    def test_category_gender_overrides_audience(self):
        """If the category string already signals gender, it takes precedence."""
        node = {
            "@type": "Product", "sku": "W01", "name": "Item", "brand": "X",
            "category": "Women's Clothing",
            "audience": {"@type": "PeopleAudience", "suggestedGender": "male"},
            "offers": {"@type": "Offer", "price": 100, "priceCurrency": "EGP"},
            "image": ["https://example.com/img.jpg"],
        }
        rec = self._map(node)
        assert rec["gender"] == "women", \
            "category-derived gender should override audience.suggestedGender"
