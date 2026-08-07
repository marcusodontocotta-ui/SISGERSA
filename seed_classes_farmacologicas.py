"""Seed das classes farmacologicas (matching por classe).

Popula classes_farmacologicas e classe_principio_ativo para que alergias
registradas na anamnese por nome de classe (ex: cefalosporinas) ou por nome
de principio ativo membro (ex: cefalexina) sejam detectadas ao checar
contra-indicacoes de alergia.

Uso: python seed_classes_farmacologicas.py
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

CLASSES = [
    ("Cefalosporinas", "Antibióticos betalactâmicos derivados das cefalosporinas.", [
        "cefalexina",
    ]),
    ("Penicilinas", "Antibióticos betalactâmicos derivados das penicilinas.", [
        "amoxicilina",
        "clavulanato de potássio",
        "amoxicilina trihidratada",
    ]),
    ("Macrolídeos", "Antibióticos macrolídeos.", [
        "azitromicina",
        "eritromicina",
    ]),
    ("Lincosamidas", "Antibióticos lincosamidas.", [
        "clindamicina",
    ]),
    ("Nitroimidazólicos", "Antibióticos nitroimidazólicos.", [
        "metronidazol",
    ]),
    ("Tetraciclinas", "Antibióticos tetraciclinas.", [
        "doxiciclina",
    ]),
    ("AINE", "Anti-inflamatórios não esteroidais (AINE).", [
        "ácido acetilsalicílico",
        "aceclofenaco",
        "cetoprofeno",
        "diclofenaco de potássio",
        "diclofenaco de sódio",
        "flurbiprofeno",
        "ibuprofeno",
        "meloxicam",
        "naproxeno",
        "nimesulida",
        "tenoxicam",
    ]),
    ("Pirazolonas", "Anti-inflamatórios derivados das pirazolonas.", [
        "dipirona",
    ]),
    ("Salicilatos", "Derivados do ácido salicílico.", [
        "ácido acetilsalicílico",
    ]),
    ("Antissépticos bucais", "Antissépticos de uso odontológico.", [
        "clorexidina",
        "digluconato de clorexidina",
        "cloreto de cetilpiridínio",
    ]),
    ("Corticosteroides", "Corticosteroides sistêmicos.", [
        "dexametasona",
        "prednisona",
    ]),
    ("Azóis antifúngicos", "Antifúngicos azóis.", [
        "cetoconazol",
        "fluconazol",
        "miconazol",
    ]),
    ("Polienos", "Antifúngicos polienos.", [
        "nistatina",
    ]),
    ("IBP", "Inibidores da bomba de prótons.", [
        "omeprazol",
        "esomeprazol magnésico",
    ]),
    ("Anestésicos locais", "Anestésicos locais.", [
        "cloridrato de lidocaina",
        "cloridrato de articaína",
        "cloridrato de mepivacaína",
        "prilocaína",
    ]),
    ("Anticoagulantes orais", "Anticoagulantes orais.", [
        "varfarina sódica",
    ]),
    ("Antiplaquetários", "Antiagregantes plaquetários.", [
        "ácido acetilsalicílico",
        "bissulfato de clopidogrel",
    ]),
]

db.execute("""
    CREATE TABLE IF NOT EXISTS classes_farmacologicas (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(100) NOT NULL UNIQUE,
        descricao VARCHAR(255),
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
db.execute("""
    CREATE TABLE IF NOT EXISTS classe_principio_ativo (
        classe_id INT NOT NULL REFERENCES classes_farmacologicas(id) ON DELETE CASCADE,
        principio_ativo_id INT NOT NULL REFERENCES principios_ativos(id) ON DELETE CASCADE,
        PRIMARY KEY (classe_id, principio_ativo_id)
    )
""")
db.execute("""
    CREATE TABLE IF NOT EXISTS reacoes_cruzadas (
        id SERIAL PRIMARY KEY,
        classe_origem_id INT NOT NULL REFERENCES classes_farmacologicas(id) ON DELETE CASCADE,
        classe_alvo_id INT NOT NULL REFERENCES classes_farmacologicas(id) ON DELETE CASCADE,
        severidade VARCHAR(20) DEFAULT 'grave',
        descricao VARCHAR(255),
        UNIQUE (classe_origem_id, classe_alvo_id)
    )
""")

# Reações cruzadas entre classes: a alergia registrada a uma classe da coluna
# "origem" também dispara alerta contra fármacos da classe "alvo".
REACOES_CRUZADAS = [
    ("Penicilinas", "Cefalosporinas", "grave",
     "Reação cruzada penicilina-cefalosporina"),
    ("Cefalosporinas", "Penicilinas", "grave",
     "Reação cruzada cefalosporina-penicilina"),
]


def resolver_pa(nome):
    r = db.fetch_one("SELECT id FROM principios_ativos WHERE LOWER(nome) = LOWER(%s) LIMIT 1", (nome,))
    return r["id"] if r else None


def main():
    for nome_classe, desc, membros in CLASSES:
        db.execute(
            """INSERT INTO classes_farmacologicas (nome, descricao)
               VALUES (%s, %s) ON CONFLICT (nome) DO NOTHING""",
            (nome_classe, desc),
        )
        r = db.fetch_one("SELECT id FROM classes_farmacologicas WHERE nome = %s", (nome_classe,))
        classe_id = r["id"]
        for m in membros:
            pa_id = resolver_pa(m)
            if pa_id is None:
                print(f"  ! PA não encontrado: {m}")
                continue
            db.execute(
                """INSERT INTO classe_principio_ativo (classe_id, principio_ativo_id)
                   VALUES (%s, %s) ON CONFLICT DO NOTHING""",
                (classe_id, pa_id),
            )
        print(f"OK classe={nome_classe} membros={len(membros)}")

    for nome_origem, nome_alvo, severidade, desc in REACOES_CRUZADAS:
        o = db.fetch_one("SELECT id FROM classes_farmacologicas WHERE nome = %s", (nome_origem,))
        a = db.fetch_one("SELECT id FROM classes_farmacologicas WHERE nome = %s", (nome_alvo,))
        if not o or not a:
            print(f"  ! Classe não encontrada para reação cruzada: {nome_origem}->{nome_alvo}")
            continue
        db.execute(
            """INSERT INTO reacoes_cruzadas (classe_origem_id, classe_alvo_id, severidade, descricao)
               VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (o["id"], a["id"], severidade, desc),
        )
        print(f"OK reacao cruzada {nome_origem} -> {nome_alvo}")

    print("\n=== Resumo ===")
    for r in db.fetch_all("""
        SELECT cl.nome AS classe, COUNT(cpa.principio_ativo_id) AS n
        FROM classes_farmacologicas cl
        LEFT JOIN classe_principio_ativo cpa ON cpa.classe_id = cl.id
        GROUP BY cl.nome ORDER BY cl.nome"""):
        print(f"   {r['classe']}: {r['n']} membros")


if __name__ == "__main__":
    main()
