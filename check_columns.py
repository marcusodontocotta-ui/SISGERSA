import psycopg
from utils.db_url import get_database_url

conn = psycopg.connect(get_database_url())
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(r[0])
cur.close()
conn.close()
