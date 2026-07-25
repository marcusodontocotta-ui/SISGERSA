import sys
import os
import logging
sys.path.insert(0, os.path.dirname(__file__))

logger = logging.getLogger("init_db")

from database.connection import db
from database.models import get_schema
from config import settings


def criar_banco():
    engine = settings.DB_ENGINE
    logger.info(f"criar_banco: engine={engine}, host={settings.DB_HOST}, port={settings.DB_PORT}, db={settings.DB_NAME}")

    schema = get_schema()
    statements = [s.strip() for s in schema.strip().split(";") if s.strip()]
    logger.info(f"criar_banco: {len(statements)} statements para executar")

    if engine == "postgresql":
        import psycopg
        try:
            conn = psycopg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                dbname=settings.DB_NAME,
                sslmode="prefer",
            )
            conn.autocommit = True
        except Exception as e:
            logger.error(f"criar_banco: falha ao conectar: {e}")
            return
    else:
        import pymysql
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset="utf8mb4",
            autocommit=True,
        )

    erros = 0
    criadas = 0
    cursor = conn.cursor()
    for i, statement in enumerate(statements):
        try:
            cursor.execute(statement)
            criadas += 1
        except Exception as e:
            erros += 1
            if erros <= 5:
                logger.warning(f"criar_banco: erro stmt {i}: {e}")
                logger.warning(f"criar_banco: sql: {statement[:150]}")
    cursor.close()
    conn.close()

    logger.info(f"criar_banco: {criadas} OK, {erros} erros")


def criar_admin_padrao():
    from utils.auth import criar_usuario
    try:
        admin_id = criar_usuario(
            nome="Administrador",
            email="marcusodontocotta@gmail.com",
            senha="admin123",
            tipo="admin",
            is_super=True,
        )
        logger.info(f"criar_admin: criado ID={admin_id}")
    except Exception as e:
        logger.info(f"criar_admin: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(f"=== Inicializando Medical DB (engine: {settings.DB_ENGINE}) ===")
    criar_banco()
    criar_admin_padrao()
    logger.info("=== Pronto! ===")
