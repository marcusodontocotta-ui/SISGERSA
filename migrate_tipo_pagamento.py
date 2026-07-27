import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa")

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
