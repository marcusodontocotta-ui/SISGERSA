import psycopg
import sys

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'

conn = psycopg.connect(PG_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute("ALTER TABLE usuarios ALTER COLUMN estado TYPE VARCHAR(5)")
print("Coluna estado alterada para VARCHAR(5)")
cur.close(); conn.close()
