import psycopg
from utils.db_url import get_database_url

conn = psycopg.connect(get_database_url())
cur = conn.cursor()
cur.execute("SELECT constraint_name, constraint_type FROM information_schema.table_constraints WHERE table_name='usuarios'")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")
cur.execute("SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name='usuarios' AND column_name='email'")
print(f"\nEmail column: {cur.fetchall()}")
cur.close(); conn.close()
