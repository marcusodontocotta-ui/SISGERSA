import psycopg

conn = psycopg.connect(
    host="dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com",
    port=5432, user="sisgersa",
    password="tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU",
    dbname="sisgersa"
)
conn.autocommit = True
cur = conn.cursor()

# Get all patients
cur.execute("SELECT id, nome FROM usuarios WHERE tipo='paciente' ORDER BY id")
pacientes = cur.fetchall()

# Get estab
cur.execute("SELECT id FROM estabelecimentos WHERE ativo=TRUE ORDER BY id")
estab = cur.fetchone()
estab_id = estab[0]

# For each patient without prontuario, create one
for pac_id, pac_nome in pacientes:
    # Link to estab
    cur.execute("INSERT INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (pac_id, estab_id))
    
    # Check if has prontuario
    cur.execute("SELECT id FROM prontuarios WHERE paciente_usuario_id=%s AND estabelecimento_id=%s", (pac_id, estab_id))
    if not cur.fetchone():
        cur.execute("SELECT COUNT(*) FROM prontuarios WHERE estabelecimento_id=%s", (estab_id,))
        total = cur.fetchone()[0]
        numero = f"PRONT-{total + 1:05d}"
        cur.execute("INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)", (pac_id, estab_id, numero))
        print(f"Criado: {pac_nome} -> {numero}")
    else:
        print(f"OK: {pac_nome} ja tem prontuario")

cur.execute("SELECT COUNT(*) FROM prontuarios WHERE estabelecimento_id=%s", (estab_id,))
print(f"\nTotal prontuarios: {cur.fetchone()[0]}")

conn.close()
