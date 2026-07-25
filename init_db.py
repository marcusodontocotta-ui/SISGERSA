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
    logger.info(f"Iniciando criacao de banco (engine={engine})")

    if engine == "postgresql":
        import psycopg
        try:
            conn = psycopg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                dbname="postgres",
                sslmode="prefer",
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.DB_NAME,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(f'CREATE DATABASE "{settings.DB_NAME}"')
                logger.info(f"Banco '{settings.DB_NAME}' criado.")
            else:
                logger.info(f"Banco '{settings.DB_NAME}' ja existe.")
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning(f"Aviso ao criar banco PostgreSQL: {e}")
    else:
        import pymysql
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            charset="utf8mb4",
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {settings.DB_NAME} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.close()

    schema = get_schema()

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
            logger.error(f"Falha ao conectar no banco {settings.DB_NAME}: {e}")
            return
    else:
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset="utf8mb4",
        )

    erros = 0
    criadas = 0
    cursor = conn.cursor()
    for statement in schema.strip().split(";"):
        statement = statement.strip()
        if statement:
            try:
                cursor.execute(statement)
                criadas += 1
            except Exception as e:
                erros += 1
                logger.warning(f"Erro ao executar SQL: {e}")
                logger.warning(f"SQL: {statement[:120]}...")
    cursor.close()
    conn.close()

    logger.info(f"Tabelas: {criadas} criadas, {erros} erros")


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
        logger.info(f"Admin criado: marcusodontocotta@gmail.com / admin123 (ID: {admin_id})")
    except Exception as e:
        logger.info(f"Admin ja existe ou erro: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(f"=== Inicializando Medical DB (engine: {settings.DB_ENGINE}) ===")
    criar_banco()
    criar_admin_padrao()
    logger.info("=== Pronto! ===")
