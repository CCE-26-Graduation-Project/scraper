import psycopg2
import json
import os
import hashlib
import uuid
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

HOST = os.getenv("HOST")
DATABASE = os.getenv("DATABASE")
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
AZURE_API_URL = os.getenv("AZURE_API_URL")
# File-relative so the checkpoint is always written next to load_products.py,
# regardless of which directory the caller runs from.
CHECKPOINT_FILE = Path(__file__).resolve().parent / ".load_products_checkpoint.json"
MAX_CONSECUTIVE_MODAL_FAILURES = int(os.getenv("MAX_CONSECUTIVE_MODAL_FAILURES", "20"))


def _connect():
    return psycopg2.connect(
        host=HOST, database=DATABASE, user=USER, password=PASSWORD,
        port=5432, sslmode="require"
    )


def fetch_db_products():
    """Return one {_id, data_hash} record per (product_url, color) row in the DB.

    ``_id`` is a composite key ``"product_url||color"`` (empty string for NULL color)
    used by the delta calculator.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT product_url, color, data_hash FROM public.products WHERE product_url IS NOT NULL"
            )
            return [
                {"_id": f"{row[0]}||{row[1] or ''}", "data_hash": row[2]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def delete_db_products(composite_ids):
    """Delete specific (product_url, color) rows identified by composite 'url||color' keys."""
    if not composite_ids:
        return
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for cid in composite_ids:
                product_url, _, color = cid.partition("||")
                if color:
                    cur.execute(
                        "DELETE FROM public.products WHERE product_url = %s AND color = %s",
                        (product_url, color),
                    )
                else:
                    cur.execute(
                        "DELETE FROM public.products WHERE product_url = %s AND color IS NULL",
                        (product_url,),
                    )
            conn.commit()
            print(f"  Deleted {len(composite_ids)} product-color rows.")
    finally:
        conn.close()


def generate_product_hash(title, price, image_url, color=None):
    """Generate a per-color content hash for change detection."""
    clean_title = str(title).strip().lower()
    clean_image = str(image_url).strip()
    clean_color = str(color).strip().lower() if color else ""

    try:
        price_float = float(price)
        if price_float.is_integer():
            clean_price = str(int(price_float))
        else:
            clean_price = f"{price_float:.2f}"
    except (ValueError, TypeError):
        clean_price = str(price).strip()

    raw_string = f"{clean_title}_{clean_price}_{clean_image}_{clean_color}".encode('utf-8')
    return hashlib.md5(raw_string).hexdigest()


def average_embeddings(image_embedding, text_embedding):
    """Element-wise average of image and text embeddings."""
    if len(image_embedding) != len(text_embedding):
        raise ValueError(
            f"Embedding length mismatch: image={len(image_embedding)}, text={len(text_embedding)}"
        )
    return [(img + txt) / 2.0 for img, txt in zip(image_embedding, text_embedding)]


def _load_checkpoints():
    if not CHECKPOINT_FILE.exists():
        return {}
    try:
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_checkpoints(checkpoints):
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoints, f, ensure_ascii=False, indent=2)


def _set_checkpoint(json_file_path, next_index):
    checkpoints = _load_checkpoints()
    checkpoints[str(Path(json_file_path).name)] = int(next_index)
    _save_checkpoints(checkpoints)


def _clear_checkpoint(json_file_path):
    checkpoints = _load_checkpoints()
    key = str(Path(json_file_path).name)
    if key in checkpoints:
        del checkpoints[key]
        _save_checkpoints(checkpoints)


def insert_products_to_db(json_file_path, products=None):
    """Insert products into public.products.

    If ``products`` is given it is used directly; otherwise the full JSON file
    is read.  Passing a pre-filtered list is how the delta-load path works.
    """

    if not AZURE_API_URL:
        print("Error: AZURE_API_URL not set in environment variables")
        return

    conn = _connect()
    cur = conn.cursor()

    if products is None:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
    
    inserted_count = 0
    failed_count = 0
    consecutive_modal_failures = 0
    stop_due_to_modal_failures = False
    checkpoint_key = str(Path(json_file_path).name)
    vendor = Path(json_file_path).stem.replace('_products', '').replace('_', ' ').title()
    start_index = int(_load_checkpoints().get(checkpoint_key, 0))

    if start_index > 0:
        print(f"Resuming {checkpoint_key} from index {start_index}...")
    
    try:
        # Insert each product with per-row commits so successful rows are never rolled back.
        for idx in range(start_index, len(products)):
            try:
                product = products[idx]
                title = (product.get('title') or '').strip()
                images = product.get('image_urls') or []
                image_url = images[0] if images else ''
                price = product.get('price', 0)
                product_url = product.get('product_url')
                colors = product.get('colors') or ['']

                if not image_url or not title:
                    _set_checkpoint(json_file_path, idx + 1)
                    continue

                # Download image bytes once — shared across all color variants.
                img_dl = requests.get(image_url, timeout=10)
                if img_dl.status_code != 200:
                    raise Exception(f"Failed to download image: {image_url}")

                # Get image embedding once per product.
                print(f"Generating embedding for: {title}...")
                try:
                    img_emb_resp = requests.post(
                        f"{AZURE_API_URL}/embed-image",
                        files={"file": ("image", img_dl.content, "image/jpeg")},
                        timeout=30
                    )
                    img_emb_resp.raise_for_status()
                    image_embedding = img_emb_resp.json()["embedding"]
                    consecutive_modal_failures = 0
                except Exception as azure_error:
                    consecutive_modal_failures += 1
                    raise RuntimeError(
                        f"Azure image embedding call failed ({consecutive_modal_failures}/{MAX_CONSECUTIVE_MODAL_FAILURES}): {azure_error}"
                    )

                # Insert one row per color.
                for color in colors:
                    product_hash = generate_product_hash(title, price, image_url, color or None)
                    text = f"{color} {title}".strip() if color else title
                    try:
                        txt_resp = requests.post(
                            f"{AZURE_API_URL}/embed-text",
                            params={"text": text},
                            timeout=30
                        )
                        txt_resp.raise_for_status()
                        text_embedding = txt_resp.json()["embedding"]
                        consecutive_modal_failures = 0
                    except Exception as azure_error:
                        consecutive_modal_failures += 1
                        print(
                            f"  Azure text embedding failed for color '{color}' of '{title}': {azure_error} "
                            f"({consecutive_modal_failures}/{MAX_CONSECUTIVE_MODAL_FAILURES})"
                        )
                        if consecutive_modal_failures >= MAX_CONSECUTIVE_MODAL_FAILURES:
                            raise RuntimeError(
                                f"Max consecutive Modal failures ({consecutive_modal_failures}) reached"
                            ) from azure_error
                        continue

                    try:
                        cur.execute(
                            """
                            INSERT INTO public.products
                            (name, price, vendor, category, product_url, image_url, color, img_emb, txt_emb, data_hash)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (product_url, color) DO NOTHING
                            RETURNING id
                            """,
                            (
                                title,
                                float(price),
                                vendor,
                                'Clothes',
                                product_url,
                                image_url,
                                color or None,
                                image_embedding,
                                text_embedding,
                                product_hash,
                            )
                        )
                        row = cur.fetchone()
                        conn.commit()

                        if row is not None:
                            inserted_count += 1
                            for img in images:
                                try:
                                    cur.execute(
                                        """
                                        INSERT INTO public.product_images (id, product_url, image_url)
                                        VALUES (%s, %s, %s)
                                        ON CONFLICT DO NOTHING
                                        """,
                                        (str(uuid.uuid4()), product_url, img)
                                    )
                                    conn.commit()
                                except Exception as img_err:
                                    print(f"  Image insert failed ({img}): {img_err}")
                                    conn.rollback()

                    except Exception as db_err:
                        print(f"  DB error for color '{color}' of '{title}': {db_err}")
                        conn.rollback()

                _set_checkpoint(json_file_path, idx + 1)

            except Exception as e:
                print(f"Error processing '{product.get('title')}': {e}")
                conn.rollback()
                failed_count += 1

                if consecutive_modal_failures >= MAX_CONSECUTIVE_MODAL_FAILURES:
                    print(
                        f"Stopping early after {consecutive_modal_failures} consecutive Modal failures. "
                        "Likely credits exhausted or service unavailable."
                    )
                    _set_checkpoint(json_file_path, idx)
                    stop_due_to_modal_failures = True
                    break

                _set_checkpoint(json_file_path, idx + 1)
                continue

        if not stop_due_to_modal_failures:
            _clear_checkpoint(json_file_path)
    except KeyboardInterrupt:
        print("Stopped by user. Already committed rows were preserved.")
        # Keep checkpoint as-is so the next run can resume.
    finally:
        cur.close()
        conn.close()
    
    print(f"Completed: {inserted_count} inserted, {failed_count} failed")
    return stop_due_to_modal_failures


def insert_all_products():
    """Process all JSON files in the repo-wide Products directory."""
    products_dir = Path(__file__).resolve().parent / "Products"
    
    if not products_dir.exists():
        print("No products directory found")
        return
    
    json_files = list(products_dir.glob("*.json"))
    
    if not json_files:
        print("No JSON files found in products directory")
        return
    
    print(f"\nInserting {len(json_files)} product files into database...")


    
    for json_file in json_files:
        print(f"\nProcessing {json_file.name}...")
        stopped = insert_products_to_db(json_file)
        if stopped:
            print("Stopped processing remaining files due to repeated Modal failures.")
            break


if __name__ == "__main__":
    insert_all_products()
