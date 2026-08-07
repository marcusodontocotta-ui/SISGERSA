"""
Cleanup: remove imported data from estab=1 and empty prontuarios from estab=4
Then re-import with estab=4 and link professionals.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg
from utils.db_url import get_database_url

DATABASE_URL = get_database_url()

t0 = time.time()
conn = psycopg.connect(DATABASE_URL, sslmode='require', connect_timeout=30)
cur = conn.cursor()

print('[%.1f] Deletando dados importados no estab=1...' % (time.time()-t0))

# 1. Delete odontograma linked to estab=1 prontuarios
cur.execute("""
    DELETE FROM odontograma WHERE prontuario_id IN (
        SELECT id FROM prontuarios WHERE estabelecimento_id = 1
    )
""")
print('  odontograma deletados: %d' % cur.rowcount)

# 2. Delete evolucoes linked to estab=1 prontuarios
cur.execute("""
    DELETE FROM evolucoes WHERE prontuario_id IN (
        SELECT id FROM prontuarios WHERE estabelecimento_id = 1
    )
""")
print('  evolucoes deletadas: %d' % cur.rowcount)

# 3. Delete consultas in estab=1
cur.execute("DELETE FROM consultas WHERE estabelecimento_id = 1")
print('  consultas deletadas: %d' % cur.rowcount)

# 4. Delete prontuarios in estab=1
cur.execute("DELETE FROM prontuarios WHERE estabelecimento_id = 1")
print('  prontuarios estab=1 deletados: %d' % cur.rowcount)

# 5. Manter os prontuarios em estab=4 (per-patient, com numero_prontuario)
#    Eles serao reutilizados no reimport

conn.commit()

print('\n[%.1f] Verificando limpeza...' % (time.time()-t0))
for t in ['prontuarios', 'consultas', 'evolucoes', 'odontograma']:
    cur.execute('SELECT count(*) FROM %s' % t)
    print('  %s: %d' % (t, cur.fetchone()[0]))

cur.close()
conn.close()
print('[%.1f] Limpeza concluida!' % (time.time()-t0))
