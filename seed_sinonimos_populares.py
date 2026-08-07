"""Seed de sinônimos populares de medicamentos.

Cria princípios ativos com nomes populares (aspirina, keflex, etc.) e os
vincula ao PA canônico via principio_sinonimos, para que alergias registradas
na anamnese pelo nome popular sejam detectadas no matching por classe.

Uso: python seed_sinonimos_populares.py
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

SINONIMOS = [
    ("aspirina", "ácido acetilsalicílico"),
    ("aas", "ácido acetilsalicílico"),
    ("keflex", "cefalexina"),
    ("amoxil", "amoxicilina"),
    ("tylenol", "paracetamol"),
    ("novalgina", "dipirona"),
    ("ibupirac", "ibuprofeno"),
    ("dalsy", "ibuprofeno"),
    ("voltaren", "diclofenaco de sódio"),
    ("flagyl", "metronidazol"),
    ("dalacin", "clindamicina"),
    ("ilosone", "eritromicina"),
    ("vibramicina", "doxiciclina"),
    ("zitromax", "azitromicina"),
    ("meticorten", "prednisona"),
    ("nexium", "esomeprazol magnésico"),
    ("luftal", "simeticona"),
    ("cataflam", "diclofenaco de potássio"),
    ("anador", "dipirona"),
    ("tachipirina", "paracetamol"),
    ("buscofem", "ibuprofeno"),
    ("alivium", "ibuprofeno"),
    ("nisulid", "nimesulida"),
    ("ponstan", "ácido mefenâmico"),
    ("profenid", "cetoprofeno"),
    ("feldene", "piroxicam"),
    ("movatec", "meloxicam"),
    ("tilatil", "tenoxicam"),
    ("decadron", "dexametasona"),
    ("predsim", "prednisolona"),
    ("zovirax", "aciclovir"),
    ("micostatin", "nistatina"),
    ("flucon", "fluconazol"),
    ("losec", "omeprazol"),
    ("celebra", "celecoxibe"),
    ("xylocaina", "lidocaína"),
    ("xylocaina", "cloridrato de lidocaina"),
    ("clavamox", "amoxicilina"),
    ("clavamox", "ácido clavulânico"),
    ("bactrim", "sulfametoxazol"),
    ("bactrim", "trimetoprima"),
]


def resolver_pa(nome):
    r = db.fetch_one("SELECT id FROM principios_ativos WHERE LOWER(nome) = LOWER(%s) LIMIT 1", (nome,))
    return r["id"] if r else None


def main():
    for sinonimo, canonico in SINONIMOS:
        can_id = resolver_pa(canonico)
        if can_id is None:
            print(f"  ! canônico não encontrado: {canonico}")
            continue
        sin_id = resolver_pa(sinonimo)
        if sin_id is None:
            db.execute(
                "INSERT INTO principios_ativos (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING",
                (sinonimo,),
            )
            sin_id = resolver_pa(sinonimo)
        if sin_id is None:
            print(f"  ! falha ao criar sinônimo: {sinonimo}")
            continue
        db.execute(
            """INSERT INTO principio_sinonimos (sinonimo_id, canonico_id)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            (sin_id, can_id),
        )
        print(f"OK {sinonimo} -> {canonico}")

    print("\n=== Resumo ===")
    for r in db.fetch_all("""
        SELECT c.nome AS canonico, COUNT(ps.id) AS n
        FROM principio_sinonimos ps
        JOIN principios_ativos c ON c.id = ps.canonico_id
        GROUP BY c.nome ORDER BY c.nome"""):
        print(f"   {r['canonico']}: {r['n']} sinônimos")


if __name__ == "__main__":
    main()
