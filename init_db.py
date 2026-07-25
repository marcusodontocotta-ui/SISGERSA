import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database.connection import db
from database.models import get_schema, SCHEMA_MYSQL
from config import settings


def criar_banco():
    engine = settings.DB_ENGINE

    if engine == "postgresql":
        import psycopg
        try:
            conn = psycopg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                dbname="postgres",
            )
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (settings.DB_NAME,))
                if not cursor.fetchone():
                    cursor.execute(f'CREATE DATABASE "{settings.DB_NAME}"')
            conn.close()
        except Exception as e:
            print(f"Aviso ao criar banco PostgreSQL: {e}")
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
        conn = psycopg.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname=settings.DB_NAME,
        )
        conn.autocommit = True
    else:
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset="utf8mb4",
        )

    cursor = conn.cursor()
    for statement in schema.strip().split(";"):
        statement = statement.strip()
        if statement:
            try:
                cursor.execute(statement)
            except Exception as e:
                print(f"Aviso: {e}")
    cursor.close()

    conn.commit()
    conn.close()
    print("Banco de dados criado com sucesso!")


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
        print(f"Admin criado: marcusodontocotta@gmail.com / admin123 (ID: {admin_id})")
        print("ATENCAO: Altere a senha padrao apos o primeiro login!")
    except Exception as e:
        print(f"Admin ja existe ou erro: {e}")


if __name__ == "__main__":
    print(f"=== Inicializando Medical DB (engine: {settings.DB_ENGINE}) ===")
    criar_banco()
    criar_admin_padrao()
    print("=== Pronto! ===")
