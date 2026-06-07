"""JSON LD extraction helpers.

Many stores embed schema.org Product data in script tags of type
application/ld+json. Reading that structured payload is far more reliable
than scraping rendered HTML, so it sits high in the extraction priority
order. This module is deliberately framework agnostic: it takes raw HTML
text and returns parsed dictionaries.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

_LD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def extract_jsonld_blocks(html: str) -> List[Any]:
    """Return every parsed JSON LD payload found in the HTML.

    Malformed blocks are skipped rather than raising, because one broken
    script tag should never take down the parse of an otherwise good page.
    """
    blocks: List[Any] = []
    if not html:
        return blocks
    for match in _LD_BLOCK.finditer(html):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except (ValueError, TypeError):
            continue
    return blocks


def _iter_nodes(payload: Any):
    """Yield every dict node, flattening lists and @graph wrappers."""
    if isinstance(payload, list):
        for entry in payload:
            yield from _iter_nodes(entry)
    elif isinstance(payload, dict):
        if "@graph" in payload and isinstance(payload["@graph"], list):
            for entry in payload["@graph"]:
                yield from _iter_nodes(entry)
        yield payload


def _has_type(node: Dict[str, Any], *wanted: str) -> bool:
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    wanted_lower = {w.lower() for w in wanted}
    return any(str(t).lower() in wanted_lower for t in types if t)


def find_product(html: str) -> Optional[Dict[str, Any]]:
    """Return the first schema.org Product node found in the HTML, if any."""
    for block in extract_jsonld_blocks(html):
        for node in _iter_nodes(block):
            if _has_type(node, "product"):
                return node
    return None


def find_product_or_group(html: str) -> Optional[Dict[str, Any]]:
    """Return the first Product or ProductGroup node found in the HTML.

    ProductGroup is the standard schema.org shape for a product that varies by
    an option (colour, size); it carries a hasVariant list of Product nodes. A
    ProductGroup is preferred when present because it gives the full variant
    set in one node. Reusable across any store that uses this pattern.
    """
    fallback: Optional[Dict[str, Any]] = None
    for block in extract_jsonld_blocks(html):
        for node in _iter_nodes(block):
            if _has_type(node, "productgroup") or node.get("hasVariant"):
                return node
            if fallback is None and _has_type(node, "product"):
                fallback = node
    return fallback


def find_product_in_graph(data: dict) -> Optional[Dict[str, Any]]:
    """Return the Product node from a JSON-LD @graph structure.

    Jumia (and some other stores) embed their Product inside a top-level
    @graph list alongside BreadcrumbList, ItemPage and Organization nodes.
    """
    graph = data.get("@graph")
    if not isinstance(graph, list):
        return None
    for node in graph:
        if isinstance(node, dict) and _has_type(node, "product"):
            return node
    return None
