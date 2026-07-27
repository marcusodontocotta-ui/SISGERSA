import psycopg
import hashlib

PG_URL = 'postgresql://sisgersa:tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU@dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com/sisgersa'
SENHA = 'Ong6132'

# Check what hash method the system uses
import sys
sys.path.insert(0, '.')
try:
    from utils.auth import hash_senha
    senha_hash = hash_senha(SENHA)
    print(f"Hash via utils.auth: {senha_hash[:30]}...")
except Exception as e:
    print(f"utils.auth error: {e}")
    senha_hash = hashlib.sha256(SENHA.encode()).hexdigest()
    print(f"Hash via sha256 fallback: {senha_hash[:30]}...")

conn = psycopg.connect(PG_URL)
conn.autocommit = False
cur = conn.cursor()

cur.execute("""
    INSERT INTO usuarios (nome, email, senha_hash, tipo, is_super, ativo)
    VALUES (%s, %s, %s, 'admin', FALSE, TRUE)
    RETURNING id
""", ("Marcus Cotta", "guiaparaoinesperado@gmail.com", senha_hash))
user_id = cur.fetchone()[0]
print(f"Admin criado: id={user_id}")

conn.commit()
cur.close(); conn.close()
print("OK!")
