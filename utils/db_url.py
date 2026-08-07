"""Obtem a URL de conexao ao banco sem embutir credenciais no codigo.

As credenciais devem vir do .env (DATABASE_URL) ou das variaveis de ambiente.
NUNCA coloque a senha de producao em arquivos de codigo/scripts.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url(require: bool = True) -> str | None:
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    dbname = os.getenv("DB_NAME")
    port = os.getenv("DB_PORT")

    if host and user and password is not None and dbname:
        return f"postgresql://{user}:{password}@{host}:{port or 5432}/{dbname}"

    if require:
        raise SystemExit(
            "Credenciais do banco nao configuradas. Defina DATABASE_URL "
            "(ou DB_HOST/DB_USER/DB_PASSWORD/DB_NAME) no .env ou no ambiente "
            "antes de rodar este script."
        )
    return None
