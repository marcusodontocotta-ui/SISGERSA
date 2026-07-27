import psycopg
conn = psycopg.connect('postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa')
cur = conn.cursor()
cur.execute("SELECT id, nome, email, tipo, is_super FROM usuarios WHERE tipo = 'admin'")
print("Todos admins:")
for r in cur.fetchall():
    print(f"  id={r[0]} | {r[1]} | {r[2]} | super={r[4]}")
cur.close(); conn.close()
