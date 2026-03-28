import psycopg2
import os
from dotenv import load_dotenv


load_dotenv()

HOST = os.getenv("HOST")
DATABASE = os.getenv("DATABASE")
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")

conn = psycopg2.connect(
    host= HOST,
    database= DATABASE,
    user= USER,
    password= PASSWORD,
    port=5432,
    sslmode="require"
)

cur = conn.cursor()

cur.execute(
    """
    INSERT INTO public.users (name, email, password_hash)
    VALUES (%s, %s, %s);
    """,
    ("Omar", "omar@example.com", "hashed_password")
)

conn.commit()

cur.execute(
    """
    SELECT * FROM public.users;
    """,
)

rows = cur.fetchall()

for row in rows:
    print(row)

cur.close()
conn.close()
