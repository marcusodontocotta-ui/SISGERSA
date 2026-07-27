import psycopg

conn = psycopg.connect('postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa')
cur = conn.cursor()

cols = [
    ("usuarios", "codigo_paciente", "VARCHAR(20)"),
    ("usuarios", "numero_documentacao", "VARCHAR(50)"),
    ("usuarios", "indicacao", "VARCHAR(200)"),
    ("usuarios", "estado_civil", "VARCHAR(30)"),
    ("usuarios", "profissao", "VARCHAR(100)"),
    ("usuarios", "nome_pai", "VARCHAR(200)"),
    ("usuarios", "nome_mae", "VARCHAR(200)"),
]

cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name='usuarios'""")
existing = {r[0] for r in cur.fetchall()}

for table, col, ctype in cols:
    if col not in existing:
        sql = f"ALTER TABLE {table} ADD COLUMN {col} {ctype}"
        cur.execute(sql)
        print(f"Adicionado: {col}")
    else:
        print(f"Ja existe: {col}")

conn.commit()
cur.close()
conn.close()
print("Done!")
