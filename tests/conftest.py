"""Shared pytest fixtures."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def shopify_payload():
    with open(FIXTURES / "shopify_products.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def hoodie(shopify_payload):
    """Multi variant fashion product (with barcodes)."""
    return shopify_payload["products"][0]


@pytest.fixture
def earbuds(shopify_payload):
    """Non fashion product."""
    return shopify_payload["products"][1]


@pytest.fixture
def dress(shopify_payload):
    """Single variant women's product (clean product level identifiers)."""
    return shopify_payload["products"][2]


@pytest.fixture
def shoes(shopify_payload):
    """Multi size athletic shoes."""
    return shopify_payload["products"][3]
