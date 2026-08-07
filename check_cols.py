import psycopg
from utils.db_url import get_database_url

PG_URL = get_database_url()
conn = psycopg.connect(PG_URL)
cur = conn.cursor()

for t in ['convenios', 'procedimentos', 'orcamentos']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s AND column_name LIKE '%%estabelecimento%%'", (t,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{t}: {cols}")

cur.close(); conn.close()
