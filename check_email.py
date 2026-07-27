import psycopg
conn = psycopg.connect('postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa')
cur = conn.cursor()
cur.execute("SELECT constraint_name, constraint_type FROM information_schema.table_constraints WHERE table_name='usuarios'")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")
cur.execute("SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name='usuarios' AND column_name='email'")
print(f"\nEmail column: {cur.fetchall()}")
cur.close(); conn.close()
