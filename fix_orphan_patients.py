"""
Script para criar prontuarios para pacientes orfos no Render
Pacientes criados pela landing page que nao possuem prontuarios.
Uso: python fix_orphan_patients.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from database.connection import db

db.get_connection()

print("=== FIX: Criando prontuarios para pacientes orfos ===\n")

pacientes_sem_pront = db.fetch_all("""
    SELECT u.id, u.nome, u.email
    FROM usuarios u
    WHERE u.tipo = 'paciente' AND u.ativo = TRUE
      AND NOT EXISTS (
          SELECT 1 FROM prontuarios p WHERE p.paciente_usuario_id = u.id
      )
""")

if not pacientes_sem_pront:
    print("Nenhum paciente orfo encontrado. Tudo certo!")
else:
    print(f"Encontrados {len(pacientes_sem_pront)} pacientes sem prontuario:")
    
    estab = db.fetch_one("SELECT id FROM estabelecimentos WHERE ativo = TRUE ORDER BY id LIMIT 1")
    if not estab:
        print("ERRO: Nenhum estabelecimento ativo encontrado!")
        sys.exit(1)
    
    estab_id = estab["id"]
    print(f"Vinculando ao estabelecimento ID={estab_id}\n")
    
    for pac in pacientes_sem_pront:
        count = db.fetch_one(
            "SELECT COUNT(*) AS total FROM prontuarios WHERE estabelecimento_id = %s",
            (estab_id,),
        )
        numero = f"PRONT-{int(count['total']) + 1:05d}"
        
        db.execute(
            "INSERT IGNORE INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s)",
            (pac["id"], estab_id),
        )
        db.execute(
            "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
            (pac["id"], estab_id, numero),
        )
        print(f"  OK: {pac['nome']} ({pac['email']}) -> {numero}")
    
    print(f"\nPronto! {len(pacientes_sem_pront)} prontuarios criados.")

total = db.fetch_one("SELECT COUNT(*) AS total FROM prontuarios")
print(f"\nTotal de prontuarios no sistema: {total['total']}")
