import os
import sys
import pymysql

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: Set DATABASE_URL environment variable"); sys.exit(1)

from urllib.parse import urlparse
parsed = urlparse(DB_URL)
c = pymysql.connect(host=parsed.hostname, user=parsed.username, password=parsed.password, database=parsed.path.lstrip("/"))
cur = c.cursor()

cur.execute("ALTER TABLE orcamentos MODIFY COLUMN status ENUM('rascunho', 'enviado', 'aprovado', 'rejeitado', 'expirado', 'pago', 'pago_parcial') DEFAULT 'rascunho'")
print("Status enum atualizado")

c.commit()
c.close()
print("OK")
