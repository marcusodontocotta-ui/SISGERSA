import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
conn = psycopg.connect(PG_URL)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='paciente'")
print(f"Total pacientes: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='paciente' AND codigo_paciente IS NOT NULL")
print(f"Com codigo: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM paciente_estabelecimento WHERE estabelecimento_id=4")
print(f"Vinculados estab 4: {cur.fetchone()[0]}")
cur.execute("SELECT MAX(id) FROM usuarios WHERE tipo='paciente'")
print(f"Ultimo ID: {cur.fetchone()[0]}")
cur.close(); conn.close()
