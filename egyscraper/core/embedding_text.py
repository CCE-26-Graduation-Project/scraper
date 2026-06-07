"""Build the text fed to the CLIP text encoder.

CLIP's text encoder truncates at 77 tokens (roughly 50 to 60 words), so the
embedding text must be compact and front loaded with the most discriminative
attributes. The builder produces a short, deterministic, structured string so
the same product always yields the same embedding text.

What is deliberately EXCLUDED to keep embeddings clean:
  * sizes, skus, barcodes, variant ids, per variant prices, stock counts.
    These are retrieval filters or commerce data, not visual or semantic
    signal. Putting "S M L XL" or a sku into the text wastes the tiny token
    budget and adds noise that pulls unrelated products together.
  * price and availability. Filters, never embedded.

What is INCLUDED, in priority order within the budget:
  gender, category, brand, title, colours, material, then a trimmed
  description tail. Colours are the normalized product level set (a union of
  variant colours), which is a genuine visual signal, not variant noise.
"""

from __future__ import annotations

from typing import Any, Dict, List

MAX_WORDS = 45

_GENDER_PHRASE = {
    "men": "men's",
    "women": "women's",
    "kids": "kids",
    "unisex": "unisex",
    "": "",
}


def _words(text: str) -> List[str]:
    return text.split()


def build_embedding_text(record: Dict[str, Any], max_words: int = MAX_WORDS) -> str:
    """Return a compact, variant free embedding string for one product record."""
    segments: List[str] = []

    gender = _GENDER_PHRASE.get((record.get("gender") or "").lower(), "")
    category = (record.get("category") or record.get("subcategory") or "").strip()
    brand = (record.get("brand") or record.get("vendor") or "").strip()
    title = (record.get("title") or "").strip()

    head = " ".join(p for p in [gender, category] if p).strip()
    if head:
        segments.append(head)
    if brand:
        segments.append(f"by {brand}")
    if title:
        segments.append(title)

    colors = [c for c in (record.get("colors") or []) if c]
    if colors:
        segments.append("color " + ", ".join(colors[:4]))

    material = [m for m in (record.get("material") or []) if m]
    if material:
        segments.append("material " + ", ".join(material[:3]))

    structured = ". ".join(segments)
    used = len(_words(structured))
    remaining = max_words - used

    description = (record.get("description") or "").strip()
    if description and remaining > 4:
        tail = " ".join(_words(description)[:remaining])
        structured = f"{structured}. {tail}"

    return " ".join(_words(structured)[:max_words]).strip()
