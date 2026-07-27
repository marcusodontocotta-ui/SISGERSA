import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
conn = psycopg.connect(PG_URL)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM paciente_estabelecimento WHERE estabelecimento_id=4")
print(f"Pacientes vinculados ao estab 4: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM prontuarios WHERE estabelecimento_id=4")
print(f"Prontuarios no estab 4: {cur.fetchone()[0]}")

cur.execute("""
    SELECT COUNT(*) FROM paciente_estabelecimento pe
    WHERE pe.estabelecimento_id = 4
    AND NOT EXISTS (SELECT 1 FROM prontuarios p WHERE p.paciente_usuario_id = pe.usuario_id AND p.estabelecimento_id = pe.estabelecimento_id)
""")
print(f"Pacientes SEM prontuario: {cur.fetchone()[0]}")

cur.close(); conn.close()
