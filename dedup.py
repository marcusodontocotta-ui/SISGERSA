import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
conn = psycopg.connect(PG_URL)
conn.autocommit = False
cur = conn.cursor()

cur.execute("""
    DELETE FROM usuarios WHERE id IN (
        SELECT id FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY codigo_paciente ORDER BY id) as rn
            FROM usuarios WHERE tipo='paciente' AND codigo_paciente IS NOT NULL
        ) t WHERE rn > 1
    )
""")
print(f"Removidos: {cur.rowcount}")

cur.execute("""
    DELETE FROM paciente_estabelecimento WHERE usuario_id NOT IN (
        SELECT id FROM usuarios WHERE tipo='paciente'
    )
""")
print(f"Orfos removidos: {cur.rowcount}")

conn.commit()

cur.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='paciente'")
print(f"Pacientes finais: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM usuarios WHERE tipo='paciente' AND codigo_paciente IS NOT NULL")
print(f"Com codigo: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM paciente_estabelecimento WHERE estabelecimento_id=4")
print(f"Vinculados estab 4: {cur.fetchone()[0]}")

cur.close(); conn.close()
