import pymysql

c = pymysql.connect(host='localhost', user='root', password='root123', database='medical_db')
cur = c.cursor()

cur.execute("ALTER TABLE orcamentos MODIFY COLUMN status ENUM('rascunho', 'enviado', 'aprovado', 'rejeitado', 'expirado', 'pago', 'pago_parcial') DEFAULT 'rascunho'")
print("Status enum atualizado")

c.commit()
c.close()
print("OK")
