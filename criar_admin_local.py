import sys
sys.path.insert(0, '.')
from utils.auth import hash_senha

senha_hash = hash_senha('Ong6132')
print(f"Hash: {senha_hash}")

import subprocess
sql = f"INSERT INTO usuarios (nome, email, senha_hash, tipo, is_super, ativo) VALUES ('Marcus Cotta', 'guiaparaoinesperado@gmail.com', '{senha_hash}', 'admin', 0, 1);"
r = subprocess.run([
    r'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe',
    '-u', 'root', '-proot123', 'medical_db', '-e', sql
], capture_output=True, text=True)
print(r.stdout)
if r.stderr: print(r.stderr)
