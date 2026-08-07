import psycopg
from utils.db_url import get_database_url

PG_URL = get_database_url()

conn = psycopg.connect(PG_URL)
conn.autocommit = False
cur = conn.cursor()

# We need a different approach - admins aren't in paciente_estabelecimento
# Let's check how admin-estab linking works
cur.execute("""SELECT column_name FROM information_schema.columns 
               WHERE table_name='usuarios' ORDER BY ordinal_position""")
cols = [r[0] for r in cur.fetchall()]
print("Colunas usuarios:", cols)

# Check if there's a relationship table for admin-estab
cur.execute("""SELECT table_name FROM information_schema.tables 
               WHERE table_name LIKE '%estab%' OR table_name LIKE '%admin%'""")
print("Tabelas relacionadas:", [r[0] for r in cur.fetchall()])

cur.close(); conn.close()
