import psycopg

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
conn = psycopg.connect(PG_URL)
cur = conn.cursor()

# Profissionais vinculados ao estab 4
cur.execute("""
    SELECT u.id, u.nome, u.tipo, u.ativo, pe.cargo
    FROM usuarios u
    JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
    WHERE pe.estabelecimento_id = 4
""")
print("=== Profissionais no estab 4 (via profissional_estabelecimento) ===")
for r in cur.fetchall():
    print(f"  id={r[0]}, nome={r[1]}, tipo={r[2]}, ativo={r[3]}, cargo={r[4]}")

# Todos os usuarios tipo profissional ativos
cur.execute("SELECT id, nome, tipo, ativo FROM usuarios WHERE tipo='profissional' AND ativo=TRUE")
print(f"\n=== Todos profissionais ativos: {cur.fetchone() or 'VAZIO'}")
for r in cur.fetchall():
    print(f"  id={r[0]}, nome={r[1]}, tipo={r[2]}, ativo={r[3]}")

# Admin vinculado ao estab 4
cur.execute("""
    SELECT u.id, u.nome, u.tipo, pe.cargo
    FROM usuarios u
    JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
    WHERE pe.estabelecimento_id = 4 AND u.tipo = 'admin'
""")
print(f"\n=== Admins vinculados ao estab 4 ===")
for r in cur.fetchall():
    print(f"  id={r[0]}, nome={r[1]}, tipo={r[2]}, cargo={r[3]}")

# Query exata do dashboard_stats
cur.execute("""
    SELECT COUNT(*) AS total FROM usuarios u
    JOIN profissional_estabelecimento pe ON pe.usuario_id = u.id
    WHERE u.tipo = 'profissional' AND u.ativo = TRUE AND pe.estabelecimento_id = 4
""")
print(f"\n=== Query dashboard_stats profissionais (estab 4): {cur.fetchone()[0]}")

cur.close(); conn.close()
