from database.db import db
db.execute("ALTER TABLE usuarios ADD COLUMN tipo_pagamento VARCHAR(20) DEFAULT 'particular'")
print("OK")
