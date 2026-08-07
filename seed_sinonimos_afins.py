"""Seed de sinônimos para nomes afins do mesmo fármaco.

Liga variantes do mesmo princípio ativo que não possuem vínculo em
principio_sinonimos (base vs sal, acentuação, variações de grafia), para que
alergias registradas por um nome disparem também para as demais grafias.

Uso: python seed_sinonimos_afins.py
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

AFINS = [
    ("lidocaína", "cloridrato de lidocaina"),
    ("cloridrato de prilocaína", "prilocaína"),
    ("ácido acetil salicilico", "ácido acetilsalicílico"),
    ("ácido acetilsalicilsalicílico", "ácido acetilsalicílico"),
    ("oxido de zinco", "óxido de zinco"),
]


def resolver_pa(nome):
    r = db.fetch_one("SELECT id FROM principios_ativos WHERE LOWER(nome) = LOWER(%s) LIMIT 1", (nome,))
    return r["id"] if r else None


def main():
    ok = 0
    for sinonimo, canonico in AFINS:
        sin_id = resolver_pa(sinonimo)
        can_id = resolver_pa(canonico)
        if sin_id is None or can_id is None:
            print(f"  ! não encontrado: {sinonimo} ({sin_id}) -> {canonico} ({can_id})")
            continue
        db.execute(
            """INSERT INTO principio_sinonimos (sinonimo_id, canonico_id)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            (sin_id, can_id),
        )
        ok += 1
        print(f"OK {sinonimo} -> {canonico}")

    print(f"\n=== {ok}/{len(AFINS)} sinônimos afins garantidos ===")


if __name__ == "__main__":
    main()
