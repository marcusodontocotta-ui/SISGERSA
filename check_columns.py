import psycopg
conn = psycopg.connect('postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(r[0])
cur.close()
conn.close()
