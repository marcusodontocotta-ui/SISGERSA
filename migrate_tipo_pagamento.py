import os
import sys
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: Set DATABASE_URL environment variable"); sys.exit(1)

conn = psycopg.connect(DATABASE_URL, sslmode="require")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tipo_pagamento VARCHAR(20) DEFAULT 'particular'")
    print("Coluna tipo_pagamento adicionada!")
    conn.commit()
except Exception as e:
    print(f"Erro: {e}")
    conn.rollback()
finally:
    cur.close()
    conn.close()
