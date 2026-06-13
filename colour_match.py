import io
import math
import os

import requests
from dotenv import load_dotenv
from PIL import Image
from rembg import remove

load_dotenv()

AZURE_API_URL = os.getenv("AZURE_API_URL")


def _cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _remove_background(image: Image.Image) -> Image.Image:
    """Strip background and composite onto white via rembg (U2Net)."""
    rgba = remove(image)
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.split()[3])
    return background


def _embed_text(text: str) -> list:
    resp = requests.post(
        f"{AZURE_API_URL}/embed-text",
        params={"text": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _embed_image(image: Image.Image) -> list:
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    buf.seek(0)
    resp = requests.post(
        f"{AZURE_API_URL}/embed-image",
        files={"file": ("image", buf, "image/jpeg")},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def match_colours_to_images(
    title: str,
    colours: list[str],
    image_urls: list[str],
) -> dict[str, list[tuple[str, list]]]:
    """Match each image URL to its closest colour using background-removed embeddings.

    1. Background is stripped from each image via rembg.
    2. The cleaned image is embedded via /embed-image.
    3. Each colour is embedded as "a {colour} {title}" via /embed-text.
    4. Cosine similarity assigns every image to its nearest colour.

    Args:
        title:      Product title used in colour prompts.
        colours:    List of colour strings (e.g. ["Black", "White", "Navy"]).
        image_urls: List of image URLs to assign.

    Returns:
        Dict mapping each colour to a list of (image_url, embedding) tuples.
    """
    if not colours:
        raise ValueError("colours list must not be empty")

    colour_embeddings = {}
    for colour in colours:
        print(f"  Embedding colour: {colour!r}")
        colour_embeddings[colour] = _embed_text(f"a {colour} {title}")

    result = {colour: [] for colour in colours}
    for image_url in image_urls:
        print(f"  Processing: {image_url.split('/files/')[-1].split('?')[0]}")
        img_dl = requests.get(image_url, timeout=10)
        if img_dl.status_code != 200:
            print(f"    Failed to download ({img_dl.status_code}), skipping.")
            continue

        image = Image.open(io.BytesIO(img_dl.content)).convert("RGB")
        cleaned = _remove_background(image)
        embedding = _embed_image(cleaned)

        best = max(colours, key=lambda c: _cosine_similarity(embedding, colour_embeddings[c]))
        result[best].append((image_url, embedding))

    return result
