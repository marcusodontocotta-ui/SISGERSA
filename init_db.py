import sys
import os
import re
import logging
sys.path.insert(0, os.path.dirname(__file__))

logger = logging.getLogger("init_db")

from database.connection import db
from database.models import get_schema, get_alter_tables
from database.schema_extra import SQL_SCHEMA_EXTRA
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

    if engine == "postgresql":
        # No Postgres, `usuarios` e uma VIEW (pacientes + profissionais). As colunas
        # de endereco/cadastro de paciente vivem na tabela base `pacientes`.
        pg_alts = [
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS logradouro VARCHAR(255)",
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS numero VARCHAR(20)",
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS complemento VARCHAR(100)",
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS bairro VARCHAR(150)",
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS cidade VARCHAR(150)",
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS estado VARCHAR(5)",
            "ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS cep VARCHAR(9)",
        ]
        for alt in pg_alts:
            try:
                cursor.execute(alt)
                criadas += 1
            except Exception as e:
                if "already exists" not in str(e):
                    logger.warning(f"criar_banco: erro pg alter: {e}")
                criadas += 1

    if engine == "mysql":
        try:
            cursor.execute("SHOW INDEX FROM usuarios WHERE Column_name = 'email' AND Key_name != 'PRIMARY'")
            idx = cursor.fetchone()
            if idx:
                cursor.execute("ALTER TABLE usuarios DROP INDEX email")
                logger.info("criar_banco: removido UNIQUE do email (usuarios)")
                criadas += 1
        except Exception as e:
            logger.warning(f"criar_banco: erro ao remover UNIQUE email: {e}")
    elif engine == "postgresql":
        try:
            cursor.execute("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'usuarios_email_key') THEN
                        ALTER TABLE usuarios DROP CONSTRAINT usuarios_email_key;
                    END IF;
                END $$;
            """)
            logger.info("criar_banco: removido UNIQUE do email (usuarios)")
            criadas += 1
        except Exception as e:
            logger.warning(f"criar_banco: erro ao remover UNIQUE email pg: {e}")

    cursor.close()
    conn.close()

    if engine == "postgresql":
        criar_schema_extra()

    logger.info(f"criar_banco: {criadas} OK, {erros} erros")


def criar_tabela_sessoes():
    engine = settings.DB_ENGINE
    if engine == "postgresql":
        stmts = [
            """CREATE TABLE IF NOT EXISTS sessoes (
                id SERIAL PRIMARY KEY,
                usuario_id INT NOT NULL,
                jti VARCHAR(64) NOT NULL UNIQUE,
                criada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revogada_em TIMESTAMP NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_sessoes_usuario ON sessoes (usuario_id)",
        ]
    else:
        stmts = [
            """CREATE TABLE IF NOT EXISTS sessoes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL,
                jti VARCHAR(64) NOT NULL,
                criada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revogada_em TIMESTAMP NULL,
                UNIQUE KEY uk_sessoes_jti (jti),
                KEY idx_sessoes_usuario (usuario_id)
            )""",
        ]
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        for stmt in stmts:
            try:
                cursor.execute(stmt)
            except Exception as e:
                logger.warning(f"criar_tabela_sessoes: erro: {e}")
        cursor.close()
        logger.info("criar_tabela_sessoes: OK")
    except Exception as e:
        logger.warning(f"criar_tabela_sessoes: falha geral: {e}")


def _coluna_existe(tabela: str, coluna: str) -> bool:
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        if settings.DB_ENGINE == "postgresql":
            cursor.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                (tabela, coluna),
            )
        else:
            cursor.execute(
                """SELECT 1 FROM information_schema.columns
                   WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s""",
                (tabela, coluna),
            )
        row = cursor.fetchone()
        cursor.close()
        return bool(row)
    except Exception:
        return False


def criar_tabelas_estado():
    """Cria tabelas de estado compartilhado entre workers (rate_limits,
    pending_logins) e garante a coluna de atividade nas sessoes."""
    engine = settings.DB_ENGINE
    if engine == "postgresql":
        stmts = [
            """CREATE TABLE IF NOT EXISTS rate_limits (
                chave VARCHAR(120) PRIMARY KEY,
                contagem INT NOT NULL DEFAULT 1,
                janela_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS pending_logins (
                session_key VARCHAR(64) PRIMARY KEY,
                user_ids TEXT NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
        ]
    else:
        stmts = [
            """CREATE TABLE IF NOT EXISTS rate_limits (
                chave VARCHAR(120) PRIMARY KEY,
                contagem INT NOT NULL DEFAULT 1,
                janela_inicio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS pending_logins (
                session_key VARCHAR(64) PRIMARY KEY,
                user_ids TEXT NOT NULL,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
        ]
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        for stmt in stmts:
            try:
                cursor.execute(stmt)
            except Exception as e:
                logger.warning(f"criar_tabelas_estado: erro: {e}")
        cursor.close()
        logger.info("criar_tabelas_estado: OK")
    except Exception as e:
        logger.warning(f"criar_tabelas_estado: falha geral: {e}")

    if not _coluna_existe("sessoes", "ultima_atividade"):
        tipo = "TIMESTAMP" if engine == "postgresql" else "DATETIME"
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE sessoes ADD COLUMN ultima_atividade {tipo} NULL")
            cursor.close()
            logger.info("criar_tabelas_estado: sessoes.ultima_atividade adicionada")
        except Exception as e:
            logger.warning(f"criar_tabelas_estado: ALTER sessoes: {e}")


def criar_schema_extra():
    if settings.DB_ENGINE != "postgresql":
        return
    try:
        import psycopg
        conn = psycopg.connect(
            host=settings.DB_HOST, port=settings.DB_PORT,
            user=settings.DB_USER, password=settings.DB_PASSWORD,
            dbname=settings.DB_NAME, sslmode="prefer",
        )
        conn.autocommit = True
        cursor = conn.cursor()

        def _split_sql(sql):
            statements = []
            i = 0
            while i < len(sql):
                while i < len(sql) and sql[i] in ' \n\r\t':
                    i += 1
                if i >= len(sql):
                    break
                if sql[i:i+2] == '--':
                    end = sql.find('\n', i)
                    i = end + 1 if end != -1 else len(sql)
                    continue
                if sql[i] == '\n':
                    i += 1
                    continue

                in_dollar = False
                dollar_tag = None
                in_string = False
                string_char = None
                start = i

                while i < len(sql):
                    ch = sql[i]

                    if not in_dollar:
                        if ch in ("'", '"') and not in_string:
                            in_string = True
                            string_char = ch
                        elif in_string and ch == string_char:
                            if i + 1 < len(sql) and sql[i+1] == string_char:
                                i += 2
                                continue
                            in_string = False
                            string_char = None

                    if not in_string:
                        if not in_dollar:
                            m = re.match(r'^\$(\w*)\$', sql[i:])
                            if m:
                                in_dollar = True
                                dollar_tag = m.group(1)
                                i += len(m.group(0))
                                continue
                        else:
                            end_tag = '$' + (dollar_tag or '') + '$'
                            if sql[i:i+len(end_tag)] == end_tag:
                                in_dollar = False
                                dollar_tag = None
                                i += len(end_tag)
                                continue

                    if ch == ';' and not in_dollar and not in_string:
                        statements.append(sql[start:i+1])
                        i += 1
                        break

                    i += 1
                else:
                    remaining = sql[start:].strip()
                    if remaining:
                        statements.append(remaining)
                    break

            return [s.strip() for s in statements if s.strip()]

        statements = _split_sql(SQL_SCHEMA_EXTRA)
        for stmt in statements:
            try:
                cursor.execute(stmt)
            except Exception as e:
                logger.warning(f"schema_extra: erro ({e}) em: {stmt[:80]}...")
        cursor.close()
        conn.close()
        logger.info("criar_schema_extra: OK (views, functions, triggers, indexes)")
    except Exception as e:
        logger.warning(f"criar_schema_extra: {e}")


def criar_admin_padrao():
    from database.connection import db
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
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE email = %s", ("marcusodontocotta@gmail.com",))
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
        else:
            import pymysql
            conn = pymysql.connect(
                host=settings.DB_HOST, port=settings.DB_PORT,
                user=settings.DB_USER, password=settings.DB_PASSWORD,
                database=settings.DB_NAME, charset="utf8mb4", autocommit=True,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE email = %s", ("marcusodontocotta@gmail.com",))
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()

        if count > 0:
            logger.info(f"criar_admin: admin ja existe ({count} registros)")
            if count > 1:
                logger.info(f"criar_admin: limpando {count - 1} duplicatas...")
                _limpar_admins_duplicados()
            return

        from utils.auth import criar_usuario
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


def _limpar_admins_duplicados():
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
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM usuarios
                WHERE email = 'marcusodontocotta@gmail.com'
                AND id NOT IN (
                    SELECT MIN(id) FROM usuarios
                    WHERE email = 'marcusodontocotta@gmail.com'
                )
            """)
            deleted = cursor.rowcount
            cursor.close()
            conn.close()
        else:
            import pymysql
            conn = pymysql.connect(
                host=settings.DB_HOST, port=settings.DB_PORT,
                user=settings.DB_USER, password=settings.DB_PASSWORD,
                database=settings.DB_NAME, charset="utf8mb4", autocommit=True,
            )
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM usuarios
                WHERE email = 'marcusodontocotta@gmail.com'
                AND id NOT IN (
                    SELECT min_id FROM (
                        SELECT MIN(id) AS min_id FROM usuarios
                        WHERE email = 'marcusodontocotta@gmail.com'
                    ) t
                )
            """)
            deleted = cursor.rowcount
            cursor.close()
            conn.close()
        logger.info(f"criar_admin: {deleted} duplicatas removidas")
    except Exception as e:
        logger.warning(f"criar_admin: erro ao limpar duplicatas: {e}")


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
            "limite_prontuarios": 30,
            "limite_orcamentos_mes": 20,
            "limite_procedimentos": 30,
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
            "limite_prontuarios": -1,
            "limite_orcamentos_mes": -1,
            "limite_procedimentos": -1,
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
            "limite_prontuarios": 200,
            "limite_orcamentos_mes": 200,
            "limite_procedimentos": 75,
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
            "limite_prontuarios": -1,
            "limite_orcamentos_mes": -1,
            "limite_procedimentos": -1,
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
            "limite_prontuarios": -1,
            "limite_orcamentos_mes": -1,
            "limite_procedimentos": -1,
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
                       limite_profissionais, limite_pacientes,
                       limite_prontuarios, limite_orcamentos_mes, limite_procedimentos, recursos)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (slug) DO NOTHING""" if engine == "postgresql"
                    else """INSERT IGNORE INTO planos (nome, slug, descricao, valor_mensal,
                       limite_estabelecimentos, limite_consultas_mes,
                       limite_profissionais, limite_pacientes,
                       limite_prontuarios, limite_orcamentos_mes, limite_procedimentos, recursos)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (p["nome"], p["slug"], p["descricao"], p["valor_mensal"],
                     p["limite_estabelecimentos"], p["limite_consultas_mes"],
                     p["limite_profissionais"], p["limite_pacientes"],
                     p["limite_prontuarios"], p["limite_orcamentos_mes"],
                     p["limite_procedimentos"], p["recursos"]),
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
