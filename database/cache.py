import sqlite3
import os
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger("cache")

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
CACHE_DB = os.path.join(CACHE_DIR, "offline_cache.db")

CACHE_TABLES = [
    "estabelecimentos",
    "usuarios",
    "profissional_estabelecimento",
    "paciente_estabelecimento",
    "convenios",
    "procedimentos",
    "procedimento_valor",
    "paciente_convenio",
    "permissoes_paciente",
    "permissoes_usuario",
    "prontuarios",
    "consultas",
    "evolucoes",
    "tratamentos",
    "odontograma",
    "imaging",
    "estoque",
    "planos",
    "cupons",
    "orcamentos",
    "orcamento_itens",
    "pagamentos",
]

DDL = """
CREATE TABLE IF NOT EXISTS cache_meta (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""

for _table in CACHE_TABLES:
    DDL += f"CREATE TABLE IF NOT EXISTS {_table} (id INTEGER PRIMARY KEY);\n"


def _get_cache_conn():
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_cache():
    conn = _get_cache_conn()
    conn.executescript(DDL)
    conn.commit()
    conn.close()
    logger.info("Cache SQLite inicializado")


def download_to_cache():
    from database.connection import db
    from config import settings

    if settings.DB_ENGINE != "postgresql":
        logger.info("Cache: engine nao e PostgreSQL, pulando")
        return False

    try:
        pg_conn = db.get_connection()
        pg_cursor = pg_conn.cursor()
    except Exception as e:
        logger.error(f"Cache: falha ao conectar Render: {e}")
        return False

    cache_conn = _get_cache_conn()
    cache_conn.executescript(DDL)

    try:
        cache_conn.execute("BEGIN")
    except Exception:
        pass

    total = 0
    for table in CACHE_TABLES:
        try:
            pg_cursor.execute(f'SELECT * FROM "{table}"')
            rows = pg_cursor.fetchall()
        except Exception as e:
            logger.warning(f"Cache [{table}]: falha ao ler: {e}")
            continue

        try:
            cache_conn.execute(f'DELETE FROM "{table}"')
        except Exception:
            pass

        if not rows:
            cache_conn.commit()
            continue

        columns = [desc[0] for desc in pg_cursor.description]
        cols_str = ", ".join([f'"{c}"' for c in columns])
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders})'

        cache_conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        col_defs = ", ".join([f'"{c}" TEXT' for c in columns])
        cache_conn.execute(f'CREATE TABLE "{table}" ({col_defs})')

        for row in rows:
            values = []
            for i, v in enumerate(row):
                if v is None:
                    values.append(None)
                else:
                    values.append(str(v))
            try:
                cache_conn.execute(insert_sql, tuple(values))
                total += 1
            except Exception as e:
                if "duplicate" not in str(e).lower():
                    logger.warning(f"Cache [{table}]: erro insert: {e}")

        cache_conn.commit()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache_conn.execute(
        "INSERT OR REPLACE INTO cache_meta (chave, valor) VALUES (?, ?)",
        ("last_sync", now),
    )
    cache_conn.commit()
    cache_conn.close()

    logger.info(f"Cache atualizado: {total} registros de {len(CACHE_TABLES)} tabelas")
    return True


def cache_query_one(sql: str, params=None):
    try:
        conn = _get_cache_conn()
        if params:
            row = conn.execute(sql, params).fetchone()
        else:
            row = conn.execute(sql).fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.warning(f"Cache query_one: {e}")
        return None


def cache_query_all(sql: str, params=None):
    try:
        conn = _get_cache_conn()
        if params:
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Cache query_all: {e}")
        return []


def get_cache_status() -> dict:
    try:
        conn = _get_cache_conn()
        row = conn.execute(
            "SELECT valor FROM cache_meta WHERE chave = 'last_sync'"
        ).fetchone()
        conn.close()
        return {"last_sync": row["valor"] if row else None}
    except Exception:
        return {"last_sync": None}


_cache_thread = None
_cache_running = False


def _background_cache(interval: int = 3600):
    global _cache_running
    _cache_running = True
    logger.info(f"Cache background: intervalo={interval}s")

    while _cache_running:
        time.sleep(interval)
        if not _cache_running:
            break

        from database.connectivity import is_online
        if not is_online():
            continue

        try:
            download_to_cache()
        except Exception as e:
            logger.error(f"Cache background erro: {e}")


def start_background_cache(interval: int = 3600):
    global _cache_thread
    init_cache()
    _cache_thread = threading.Thread(
        target=_background_cache,
        args=(interval,),
        daemon=True,
        name="cache-sqlite",
    )
    _cache_thread.start()
    logger.info("Background cache iniciado")


def stop_background_cache():
    global _cache_running
    _cache_running = False
    logger.info("Background cache parado")
