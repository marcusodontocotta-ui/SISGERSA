import psycopg
conn = psycopg.connect('postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa')
cur = conn.cursor()

print("=== ESTABELECIMENTOS ===")
cur.execute("SELECT id, nome, tipo, cnpj, telefone, email, endereco, ativo FROM estabelecimentos ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]} | {r[1]} | tipo={r[2]} | cnpj={r[3]} | tel={r[4]} | email={r[5]}")

print("\n=== ADMINS ===")
cur.execute("SELECT id, nome, email, tipo, is_super FROM usuarios WHERE tipo='admin'")
for r in cur.fetchall():
    print(f"  id={r[0]} | {r[1]} | {r[2]} | super={r[4]}")

print("\n=== TOTAL PACIENTES POR ESTAB ===")
cur.execute("""SELECT e.id, e.nome, COUNT(*) as total
               FROM estabelecimentos e
               JOIN paciente_estabelecimento pe ON pe.estabelecimento_id = e.id
               GROUP BY e.id, e.nome""")
for r in cur.fetchall():
    print(f"  estab {r[0]} ({r[1]}): {r[2]} pacientes")

cur.close(); conn.close()
