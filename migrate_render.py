import os
import sys
import psycopg

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: Set DATABASE_URL environment variable"); sys.exit(1)

conn = psycopg.connect(DB_URL, sslmode="require")
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

from psycopg.sql import SQL, Identifier

cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name='usuarios'""")
existing = {r[0] for r in cur.fetchall()}

for table, col, ctype in cols:
    if col not in existing:
        cur.execute(SQL("ALTER TABLE {} ADD COLUMN {} {}").format(Identifier(table), Identifier(col), SQL(ctype)))
        print(f"Adicionado: {col}")
    else:
        print(f"Ja existe: {col}")

conn.commit()
cur.close()
conn.close()
print("Done!")
