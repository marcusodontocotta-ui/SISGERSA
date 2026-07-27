import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
conn = psycopg.connect(PG_URL)
cur = conn.cursor()

for t in ['convenios', 'procedimentos', 'orcamentos']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s AND column_name LIKE '%%estabelecimento%%'", (t,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{t}: {cols}")

cur.close(); conn.close()
