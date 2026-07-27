import psycopg
import sys

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
ESTAB_ID = 4
BATCH = 300

conn = psycopg.connect(PG_URL)
conn.autocommit = False
cur = conn.cursor()

print("1. Buscando pacientes sem prontuario no estab 4...")
sys.stdout.flush()

cur.execute("""
    SELECT pe.usuario_id, pe.estabelecimento_id
    FROM paciente_estabelecimento pe
    WHERE pe.estabelecimento_id = %s
    AND NOT EXISTS (
        SELECT 1 FROM prontuarios p
        WHERE p.paciente_usuario_id = pe.usuario_id
        AND p.estabelecimento_id = pe.estabelecimento_id
    )
""", (ESTAB_ID,))
pacientes = cur.fetchall()
print(f"   {len(pacientes)} pacientes sem prontuario")
sys.stdout.flush()

print("2. Buscando maior numero de prontuario existente...")
sys.stdout.flush()
cur.execute("SELECT COUNT(*) FROM prontuarios WHERE estabelecimento_id = %s", (ESTAB_ID,))
start = cur.fetchone()[0]
print(f"   Prontuarios ja existentes: {start}")
sys.stdout.flush()

print("3. Criando prontuarios...")
sys.stdout.flush()
created = 0

for i in range(0, len(pacientes), BATCH):
    batch = pacientes[i:i+BATCH]
    try:
        args = []
        for j, (pac_id, eid) in enumerate(batch):
            num = f"PRONT-{start + i + j + 1:05d}"
            args.append((pac_id, eid, num))

        cur.executemany(
            "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
            args
        )
        conn.commit()
        created += len(batch)
        print(f"   ... {created}/{len(pacientes)}")
        sys.stdout.flush()
    except Exception as e:
        conn.rollback()
        print(f"ERRO batch {i}: {e}")
        sys.stdout.flush()

print(f"\n=== RESULTADO ===")
cur.execute("SELECT COUNT(*) FROM prontuarios WHERE estabelecimento_id = %s", (ESTAB_ID,))
print(f"Total prontuarios no estab 4: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM paciente_estabelecimento WHERE estabelecimento_id = %s", (ESTAB_ID,))
print(f"Total pacientes no estab 4: {cur.fetchone()[0]}")

cur.close(); conn.close()
