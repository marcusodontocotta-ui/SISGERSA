import os
import sys
sys.path.insert(0, '.')

from utils.auth import hash_senha

senha_hash = hash_senha('Ong6132')
print(f"Hash gerado: {senha_hash[:20]}...")

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: Set DATABASE_URL environment variable"); sys.exit(1)

from urllib.parse import urlparse
parsed = urlparse(DB_URL)

if parsed.scheme.startswith("postgres"):
    import psycopg
    conn = psycopg.connect(DB_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO profissionais (nome, email, senha_hash, ativo, is_admin_geral, is_super, is_admin_estabelecimento) "
        "VALUES (%s, %s, %s, TRUE, TRUE, TRUE, TRUE) RETURNING id",
        ('Marcus Cotta', 'guiaparaoinesperado@gmail.com', senha_hash),
    )
    print(f"Admin criado com ID: {cur.fetchone()[0]}")
    conn.commit()
    cur.close()
    conn.close()
else:
    import pymysql
    conn = pymysql.connect(host=parsed.hostname, user=parsed.username, password=parsed.password, database=parsed.path.lstrip("/"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO profissionais (nome, email, senha_hash, ativo, is_admin_geral, is_super, is_admin_estabelecimento) "
        "VALUES (%s, %s, %s, 1, 1, 1, 1)",
        ('Marcus Cotta', 'guiaparaoinesperado@gmail.com', senha_hash),
    )
    print(f"Admin criado com ID: {cur.lastrowid}")
    conn.commit()
    cur.close()
    conn.close()
