import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
conn = psycopg.connect(PG_URL)
cur = conn.cursor()

for estab_id in [1, 4]:
    cur.execute("SELECT COUNT(*) FROM prontuarios WHERE estabelecimento_id = %s", (estab_id,))
    pront = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM paciente_estabelecimento WHERE estabelecimento_id = %s", (estab_id,))
    pe = cur.fetchone()[0]
    print(f"Estab {estab_id}: prontuarios={pront}, paciente_estabelecimento={pe}")

cur.execute("SELECT COUNT(*) FROM prontuarios")
print(f"Total prontuarios: {cur.fetchone()[0]}")
cur.execute("SELECT estabelecimento_id, COUNT(*) FROM prontuarios GROUP BY estabelecimento_id")
for r in cur.fetchall():
    print(f"  estab {r[0]}: {r[1]} prontuarios")

cur.close(); conn.close()
