"""Seed de contra-indicacoes de alergia padrao.

Preenche lacunas de dados: PAs curados (com indicacao/efeito/interacao/contra)
que nao possuem nenhum registro tipo='alergia' em contra_indicacoes. Isso
permite que alergias registradas na anamnese disparem alerta para esses
farmacos (ex: alergia a azitromicina, a tylenol, etc.).

Regra de descricao:
  - 1 classe farmacologica -> "Alergia a {classe}" (ex: Alergia a Macrolideos)
  - sem classe ou multiplas classes -> "Alergia a {nome do PA}"

Uso: python seed_alergias_padrao.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("DB_ENGINE", "postgresql")

from config import settings  # noqa: E402  credenciais via .env ou ambiente

if not settings.DATABASE_URL and not settings.DB_PASSWORD:
    raise SystemExit(
        "Credenciais do banco nao configuradas. Defina DATABASE_URL "
        "(ou DB_HOST/DB_USER/DB_PASSWORD/DB_NAME) no .env ou no ambiente."
    )

from database.connection import db

from utils.farmaco import expandir_sinonimos  # noqa: E402


# PAs sem vínculos de "curado" (sem indicacao/efeito/interacao) que o filtro
# acima ignora, mas que também precisam de registro de alergia para que os
# sinônimos populares correspondentes disparem alerta (ex: ponstan, zovirax,
# bactrim). Nomes apontados para sinônimos são resolvidos para o canônico.
EXTRAS = [
    "diclofenaco potássico",
    "ácido mefenâmico",
    "aciclovir",
    "sulfametoxazol",
]


def _garantir_alergia(pa_id, nome):
    ja_tem = db.fetch_one(
        "SELECT id FROM contra_indicacoes WHERE principio_ativo_id=%s AND tipo='alergia' LIMIT 1",
        (pa_id,),
    )
    if ja_tem:
        print(f"  = id={pa_id:<5} {nome:<45} já possui alergia registrada")
        return False
    desc = f"Alergia a {nome}"
    db.execute(
        """INSERT INTO contra_indicacoes (principio_ativo_id, tipo, descricao, severidade)
           VALUES (%s, 'alergia', %s, 'grave')""",
        (pa_id, desc),
    )
    return True


def main():
    inseridos = 0
    pulados = 0
    sem_alergia = db.fetch_all("""
        SELECT * FROM (
            SELECT p.id, p.nome,
                   (SELECT COUNT(*) FROM contra_indicacoes c
                     WHERE c.principio_ativo_id=p.id AND c.tipo='alergia') AS n_alergia,
                   (SELECT COUNT(*) FROM classe_principio_ativo cpa
                     WHERE cpa.principio_ativo_id=p.id) AS n_classes
            FROM principios_ativos p
            WHERE EXISTS (SELECT 1 FROM indicacoes i WHERE i.principio_ativo_id=p.id)
               OR EXISTS (SELECT 1 FROM efeitos_colaterais e WHERE e.principio_ativo_id=p.id)
               OR EXISTS (SELECT 1 FROM interacoes_medicamentosas im
                          WHERE im.medicamento_a_id=p.id OR im.medicamento_b_id=p.id)
               OR EXISTS (SELECT 1 FROM contra_indicacoes c WHERE c.principio_ativo_id=p.id)
        ) t WHERE n_alergia = 0 ORDER BY nome""")

    if not sem_alergia:
        print("Nenhum PA sem registro de alergia. Nada a fazer.")
    else:
        for r in sem_alergia:
            classes = db.fetch_all(
                "SELECT cl.nome FROM classe_principio_ativo cpa "
                "JOIN classes_farmacologicas cl ON cl.id = cpa.classe_id "
                "WHERE cpa.principio_ativo_id = %s ORDER BY cl.nome",
                (r["id"],),
            )
            if len(classes) == 1:
                desc = f"Alergia a {classes[0]['nome']}"
            else:
                desc = f"Alergia a {r['nome']}"
            db.execute(
                """INSERT INTO contra_indicacoes (principio_ativo_id, tipo, descricao, severidade)
                   VALUES (%s, 'alergia', %s, 'grave') ON CONFLICT DO NOTHING""",
                (r["id"], desc),
            )
            inseridos += 1
            print(f"OK id={r['id']:<5} {r['nome']:<45} -> {desc}")

    for nome in EXTRAS:
        p = db.fetch_one("SELECT id, nome FROM principios_ativos WHERE LOWER(nome)=LOWER(%s) LIMIT 1", (nome,))
        if not p:
            print(f"  ! PA não encontrado: {nome}")
            continue
        canonico_ids = expandir_sinonimos({p["id"]})
        alvo_id = p["id"]
        alvo_nome = p["nome"]
        if canonico_ids:
            alvo_id = sorted(canonico_ids)[0]
            alvo_nome = db.fetch_one("SELECT nome FROM principios_ativos WHERE id=%s", (alvo_id,))["nome"]
        if _garantir_alergia(alvo_id, alvo_nome):
            inseridos += 1
            print(f"OK id={alvo_id:<5} {alvo_nome:<45} -> Alergia a {alvo_nome} (extras)")
        else:
            pulados += 1

    print(f"\n=== {inseridos} alergias inseridas, {pulados} puladas ===")


if __name__ == "__main__":
    main()
