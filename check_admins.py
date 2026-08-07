import psycopg
from utils.db_url import get_database_url

conn = psycopg.connect(get_database_url())
cur = conn.cursor()
cur.execute("SELECT id, nome, email, tipo, is_super FROM usuarios WHERE tipo = 'admin'")
print("Todos admins:")
for r in cur.fetchall():
    print(f"  id={r[0]} | {r[1]} | {r[2]} | super={r[4]}")
cur.close(); conn.close()
