import psycopg
from utils.db_url import get_database_url

PG_URL = get_database_url()
conn = psycopg.connect(PG_URL)
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT id FROM usuarios WHERE email = 'guiaparaoinesperado@gmail.com'")
admin = cur.fetchone()
if admin:
    admin_id = admin[0]
    print(f"Admin id: {admin_id}")
    
    cur.execute("SELECT id FROM profissional_estabelecimento WHERE usuario_id = %s AND estabelecimento_id = 4", (admin_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id, cargo) VALUES (%s, 4, 'Administrador')", (admin_id,))
        print("Vinculado ao estab 4!")
    else:
        print("Ja vinculado")
    
    conn.commit()
else:
    print("Admin nao encontrado")

cur.execute("SELECT pe.usuario_id, pe.estabelecimento_id, e.nome FROM profissional_estabelecimento pe JOIN estabelecimentos e ON e.id = pe.estabelecimento_id WHERE pe.usuario_id = %s", (admin_id,) if admin else (0,))
print("Vinculos:")
for r in cur.fetchall():
    print(f"  user={r[0]} -> estab {r[1]} ({r[2]})")

cur.close(); conn.close()
