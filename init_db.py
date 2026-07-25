import sys
import os
import logging
sys.path.insert(0, os.path.dirname(__file__))

logger = logging.getLogger("init_db")

from database.connection import db
from database.models import get_schema, get_alter_tables
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

    for alter in get_alter_tables():
        try:
            cursor.execute(alter)
            criadas += 1
        except Exception as e:
            if "Duplicate column" not in str(e) and "already exists" not in str(e):
                logger.warning(f"criar_banco: erro alter: {e}")
            criadas += 1

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


def seed_planos():
    planos = [
        {
            "nome": "Gratis",
            "slug": "gratis",
            "descricao": "Ideal para profissionais autônomos começando a organizar seus atendimentos.",
            "valor_mensal": 0,
            "limite_estabelecimentos": 1,
            "limite_consultas_mes": 50,
            "limite_profissionais": 2,
            "limite_pacientes": 30,
            "recursos": "Prontuário eletrônico,Agendamento,Relatórios básicos",
        },
        {
            "nome": "Cortesia",
            "slug": "cortesia",
            "descricao": "Plano especial para parceiros e colaboradores do SISGERSA. Acesso completo.",
            "valor_mensal": 0,
            "limite_estabelecimentos": 5,
            "limite_consultas_mes": -1,
            "limite_profissionais": 20,
            "limite_pacientes": 1000,
            "recursos": "Tudo do Profissional,Suporte prioritário,Multi-estabelecimento",
        },
        {
            "nome": "Basico",
            "slug": "basico",
            "descricao": "Para clínicas pequenas com até 3 profissionais.",
            "valor_mensal": 99.00,
            "limite_estabelecimentos": 2,
            "limite_consultas_mes": 500,
            "limite_profissionais": 5,
            "limite_pacientes": 200,
            "recursos": "Tudo do Gratis,Orçamentos,Pagamentos,Relatórios financeiros,Convênios",
        },
        {
            "nome": "Profissional",
            "slug": "profissional",
            "descricao": "Para clínicas em crescimento com múltiplos profissionais.",
            "valor_mensal": 249.00,
            "limite_estabelecimentos": 5,
            "limite_consultas_mes": -1,
            "limite_profissionais": 20,
            "limite_pacientes": 1000,
            "recursos": "Tudo do Básico,Multi-estabelecimento,Nota fiscal,Agenda semanal,Relatórios avançados",
        },
        {
            "nome": "Enterprise",
            "slug": "enterprise",
            "descricao": "Para redes de clínicas e hospitais.",
            "valor_mensal": 499.00,
            "limite_estabelecimentos": -1,
            "limite_consultas_mes": -1,
            "limite_profissionais": -1,
            "limite_pacientes": -1,
            "recursos": "Tudo do Profissional,Suporte dedicado,API acesso,Backup automático,Customizações",
        },
    ]

    engine = settings.DB_ENGINE
    try:
        if engine == "postgresql":
            import psycopg
            conn = psycopg.connect(
                host=settings.DB_HOST, port=settings.DB_PORT,
                user=settings.DB_USER, password=settings.DB_PASSWORD,
                dbname=settings.DB_NAME, sslmode="prefer",
            )
            conn.autocommit = True
        else:
            import pymysql
            conn = pymysql.connect(
                host=settings.DB_HOST, port=settings.DB_PORT,
                user=settings.DB_USER, password=settings.DB_PASSWORD,
                database=settings.DB_NAME, charset="utf8mb4", autocommit=True,
            )

        cursor = conn.cursor()
        for p in planos:
            try:
                cursor.execute(
                    """INSERT INTO planos (nome, slug, descricao, valor_mensal,
                       limite_estabelecimentos, limite_consultas_mes,
                       limite_profissionais, limite_pacientes, recursos)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (slug) DO NOTHING""" if engine == "postgresql"
                    else """INSERT IGNORE INTO planos (nome, slug, descricao, valor_mensal,
                       limite_estabelecimentos, limite_consultas_mes,
                       limite_profissionais, limite_pacientes, recursos)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (p["nome"], p["slug"], p["descricao"], p["valor_mensal"],
                     p["limite_estabelecimentos"], p["limite_consultas_mes"],
                     p["limite_profissionais"], p["limite_pacientes"], p["recursos"]),
                )
            except Exception as e:
                logger.warning(f"seed_planos: erro ao inserir {p['slug']}: {e}")
        cursor.close()
        conn.close()
        logger.info("seed_planos: OK")
    except Exception as e:
        logger.warning(f"seed_planos: falha geral: {e}")


def seed_cupons():
    cupons = [
        {
            "codigo": "PRIMEIRO50",
            "descricao": "50% de desconto no primeiro mes para novos clientes",
            "desconto_percentual": 50,
            "plano_destino": "basico",
            "validade_dias": 90,
            "max_usos": 100,
        },
        {
            "codigo": "PARCEIRO",
            "descricao": "Acesso completo cortesia para parceiros comerciais",
            "desconto_percentual": 100,
            "plano_destino": "profissional",
            "validade_dias": 365,
            "max_usos": 0,
        },
        {
            "codigo": "LANCAMENTO",
            "descricao": "Promocao de lancamento - 30% off no primeiro ano",
            "desconto_percentual": 30,
            "plano_destino": "basico",
            "validade_dias": 180,
            "max_usos": 200,
        },
    ]

    engine = settings.DB_ENGINE
    try:
        if engine == "postgresql":
            import psycopg
            conn = psycopg.connect(
                host=settings.DB_HOST, port=settings.DB_PORT,
                user=settings.DB_USER, password=settings.DB_PASSWORD,
                dbname=settings.DB_NAME, sslmode="prefer",
            )
            conn.autocommit = True
        else:
            import pymysql
            conn = pymysql.connect(
                host=settings.DB_HOST, port=settings.DB_PORT,
                user=settings.DB_USER, password=settings.DB_PASSWORD,
                database=settings.DB_NAME, charset="utf8mb4", autocommit=True,
            )

        cursor = conn.cursor()
        for c in cupons:
            try:
                cursor.execute(
                    """INSERT INTO cupons (codigo, descricao, desconto_percentual,
                       plano_destino, validade_dias, max_usos)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (codigo) DO NOTHING""" if engine == "postgresql"
                    else """INSERT IGNORE INTO cupons (codigo, descricao, desconto_percentual,
                       plano_destino, validade_dias, max_usos)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (c["codigo"], c["descricao"], c["desconto_percentual"],
                     c["plano_destino"], c["validade_dias"], c["max_usos"]),
                )
            except Exception as e:
                logger.warning(f"seed_cupons: erro ao inserir {c['codigo']}: {e}")
        cursor.close()
        conn.close()
        logger.info("seed_cupons: OK")
    except Exception as e:
        logger.warning(f"seed_cupons: falha geral: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(f"=== Inicializando Medical DB (engine: {settings.DB_ENGINE}) ===")
    criar_banco()
    criar_admin_padrao()
    seed_planos()
    seed_cupons()
    logger.info("=== Pronto! ===")
