import psycopg2
conn = psycopg2.connect(
    host='dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com',
    port=5432,
    user='sisgersa',
    password='tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU',
    dbname='sisgersa'
)
cur = conn.cursor()

print('=== TABLES LIKE %orcamento% ===')
cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_name LIKE '%orcamento%' ORDER BY table_name, ordinal_position")
for row in cur.fetchall():
    print(f'  {row[0]}.{row[1]} ({row[2]})')

print()
print('=== COUNT orcamentos ===')
cur.execute('SELECT COUNT(*) FROM orcamentos')
print(f'  COUNT orcamentos: {cur.fetchone()[0]}')

print()
print('=== COUNT orcamento_itens ===')
cur.execute('SELECT COUNT(*) FROM orcamento_itens')
print(f'  COUNT orcamento_itens: {cur.fetchone()[0]}')

print()
print('=== orcamentos LIMIT 3 ===')
cur.execute('SELECT * FROM orcamentos LIMIT 3')
cols = [desc[0] for desc in cur.description]
print(f'  Columns: {cols}')
for row in cur.fetchall():
    print(f'  {row}')

print()
print('=== orcamento_itens LIMIT 5 ===')
cur.execute('SELECT * FROM orcamento_itens LIMIT 5')
cols = [desc[0] for desc in cur.description]
print(f'  Columns: {cols}')
for row in cur.fetchall():
    print(f'  {row}')

print()
print('=== pagamentos LIMIT 5 ===')
cur.execute('SELECT * FROM pagamentos LIMIT 5')
cols = [desc[0] for desc in cur.description]
print(f'  Columns: {cols}')
for row in cur.fetchall():
    print(f'  {row}')

cur.close()
conn.close()
print('\nDone.')
