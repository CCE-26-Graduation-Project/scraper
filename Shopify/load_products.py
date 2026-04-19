import psycopg2
import json
import os
from pathlib import Path
from dotenv import load_dotenv
import modal
import requests

load_dotenv()

HOST = os.getenv("HOST")
DATABASE = os.getenv("DATABASE")
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
CHECKPOINT_FILE = Path(".load_products_checkpoint.json")
MAX_CONSECUTIVE_MODAL_FAILURES = int(os.getenv("MAX_CONSECUTIVE_MODAL_FAILURES", "20"))


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


def insert_products_to_db(json_file_path):
    """Read products from JSON and insert into public.products table"""

    try:
        ClipModel = modal.Cls.from_name("clip-service", "ClipModel")
        model = ClipModel()
    except Exception as e:
        print(f"Error: Modal service not found. Did you run 'modal deploy app.py'?\n{e}")
        return
    
    conn = psycopg2.connect(
        host=HOST,
        database=DATABASE,
        user=USER,
        password=PASSWORD,
        port=5432,
        sslmode="require"
    )

    cur = conn.cursor()
    
    # Read the JSON file
    with open(json_file_path, 'r', encoding='utf-8') as f:
        products = json.load(f)
    
    inserted_count = 0
    failed_count = 0
    consecutive_modal_failures = 0
    stop_due_to_modal_failures = False
    checkpoint_key = str(Path(json_file_path).name)
    start_index = int(_load_checkpoints().get(checkpoint_key, 0))

    if start_index > 0:
        print(f"Resuming {checkpoint_key} from index {start_index}...")
    
    try:
        # Insert each product with per-row commits so successful rows are never rolled back.
        for idx in range(start_index, len(products)):
            try:
                product = products[idx]
                title = (product.get('title') or '').strip()
                image_url = product.get('images', [''])[0]
                if not image_url or not title:
                    _set_checkpoint(json_file_path, idx + 1)
                    continue

                # 1. Download image bytes
                img_response = requests.get(image_url, timeout=10)
                if img_response.status_code != 200:
                    raise Exception(f"Failed to download image: {image_url}")

                # 2. Get image + text embeddings from Modal GPU and average them
                print(f"Generating embedding for: {title}...")
                try:
                    image_embedding = model.get_image_embedding.remote(img_response.content)
                    text_embedding = model.get_text_embedding.remote(title)
                    consecutive_modal_failures = 0
                except Exception as modal_error:
                    consecutive_modal_failures += 1
                    raise RuntimeError(
                        f"Modal embedding call failed ({consecutive_modal_failures}/{MAX_CONSECUTIVE_MODAL_FAILURES}): {modal_error}"
                    )

                # embedding = average_embeddings(image_embedding, text_embedding)

                print(len(image_embedding))
                print(len(text_embedding))


                cur.execute(
                    """
                    INSERT INTO public.products 
                    (name, price, vendor, category, product_url, image_url, img_emb, txt_emb)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        title,
                        float(product.get('price', 0)),
                        product.get('vendor'),
                        'Clothes',
                        product.get('url'),
                        product.get('images', [''])[0],  # First image
                        image_embedding,  # Use the actual image embedding
                        text_embedding   # Use the actual text embedding
                    )
                )
                conn.commit()
                inserted_count += 1
                _set_checkpoint(json_file_path, idx + 1)

            except Exception as e:
                print(f"Error inserting {product.get('title')}: {e}")
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
    """Process all JSON files in the products directory"""
    products_dir = Path("products")
    
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
