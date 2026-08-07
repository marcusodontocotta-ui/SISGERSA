import psycopg
import sys
from utils.db_url import get_database_url

PG_URL = get_database_url()

conn = psycopg.connect(PG_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute("ALTER TABLE usuarios ALTER COLUMN estado TYPE VARCHAR(5)")
print("Coluna estado alterada para VARCHAR(5)")
cur.close(); conn.close()
