import psycopg2
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST")
DATABASE = os.getenv("DATABASE")
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")


def insert_products_to_db(json_file_path):
    """Read products from JSON and insert into public.products table"""
    
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
    
    # Insert each product
    for product in products:
        try:
            cur.execute(
                """
                INSERT INTO public.products 
                (name, price, vendor, category, product_url, image_url, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    product.get('title'),
                    float(product.get('price', 0)),
                    product.get('vendor'),
                    'Clothes',
                    product.get('url'),
                    product.get('images', [''])[0],  # First image
                    [0.0] * 512  # 512-dimensional zero vector
                )
            )
            inserted_count += 1
        except Exception as e:
            print(f"Error inserting {product.get('title')}: {e}")
            conn.rollback()
            failed_count += 1
            continue
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Completed: {inserted_count} inserted, {failed_count} failed")


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
        insert_products_to_db(json_file)


if __name__ == "__main__":
    insert_all_products()
