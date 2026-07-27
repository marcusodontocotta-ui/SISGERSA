import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'

conn = psycopg.connect(PG_URL)
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT id FROM usuarios WHERE tipo='paciente'")
ids = [r[0] for r in cur.fetchall()]
print(f"Removendo TODOS os {len(ids)} pacientes...")

if ids:
    cur.execute("DELETE FROM paciente_estabelecimento WHERE usuario_id = ANY(%s)", (ids,))
    cur.execute("DELETE FROM usuarios WHERE id = ANY(%s)", (ids,))
    conn.commit()

cur.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='paciente'")
print(f"Pacientes restantes: {cur.fetchone()[0]}")

cur.close(); conn.close()
