import os
import psycopg
import sys

PG_URL = os.getenv("DATABASE_URL")
if not PG_URL:
    print("ERROR: Set DATABASE_URL environment variable"); sys.exit(1)

conn = psycopg.connect(PG_URL, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

alts = [
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS logradouro VARCHAR(255)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS numero VARCHAR(20)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS complemento VARCHAR(100)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bairro VARCHAR(150)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS cidade VARCHAR(150)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS estado VARCHAR(2)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS cep VARCHAR(9)",
]

for alt in alts:
    try:
        cur.execute(alt)
        print(f"OK: {alt.split('IF NOT EXISTS ')[1]}")
    except Exception as e:
        print(f"ERRO: {alt} -> {e}")

cur.close(); conn.close()
print("\nColunas adicionadas!")
