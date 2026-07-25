import os
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger("backup")

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backups")
MAX_BACKUPS = 30


def dump_database():
    from config import settings

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if settings.DB_ENGINE == "postgresql":
        dump_file = os.path.join(BACKUP_DIR, f"sisgersa_{timestamp}.sql")
        return _dump_postgresql(settings, dump_file)
    else:
        dump_file = os.path.join(BACKUP_DIR, f"sisgersa_{timestamp}.sql")
        return _dump_mysql(settings, dump_file)


def _dump_postgresql(settings, dump_file: str) -> str:
    try:
        import psycopg
        conn = psycopg.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname=settings.DB_NAME,
            sslmode="prefer",
        )

        tables = []
        cur = conn.cursor()
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' ORDER BY tablename
        """)
        for row in cur.fetchall():
            tables.append(row[0])
        cur.close()

        with open(dump_file, "w", encoding="utf-8") as f:
            f.write(f"-- SISGERSA Backup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"-- Database: {settings.DB_NAME}\n\n")

            for table in tables:
                try:
                    cur = conn.cursor()
                    cur.execute(f'SELECT * FROM "{table}"')
                    rows = cur.fetchall()
                    cols = [desc[0] for desc in cur.description]
                    cur.close()

                    if not rows:
                        continue

                    f.write(f'-- Tabela: {table}\n')
                    f.write(f'DELETE FROM "{table}";\n')

                    cols_str = ", ".join([f'"{c}"' for c in cols])
                    for row in rows:
                        vals = []
                        for v in row:
                            if v is None:
                                vals.append("NULL")
                            elif isinstance(v, bool):
                                vals.append("TRUE" if v else "FALSE")
                            elif isinstance(v, (int, float)):
                                vals.append(str(v))
                            else:
                                escaped = str(v).replace("'", "''")
                                vals.append(f"'{escaped}'")
                        f.write(f'INSERT INTO "{table}" ({cols_str}) VALUES ({", ".join(vals)});\n')
                    f.write("\n")
                except Exception as e:
                    f.write(f"-- ERRO ao exportar {table}: {e}\n\n")

        conn.close()
        logger.info(f"Backup PostgreSQL: {dump_file}")
        return dump_file

    except Exception as e:
        logger.error(f"Backup PostgreSQL falhou: {e}")
        return None


def _dump_mysql(settings, dump_file: str) -> str:
    try:
        import pymysql
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [list(row.values())[0] for row in cur.fetchall()]

        with open(dump_file, "w", encoding="utf-8") as f:
            f.write(f"-- SISGERSA Backup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"-- Database: {settings.DB_NAME}\n\n")
            f.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

            for table in tables:
                cur.execute(f"SELECT * FROM `{table}`")
                rows = cur.fetchall()
                if not rows:
                    continue
                cols = list(rows[0].keys())

                f.write(f"-- Tabela: {table}\n")
                f.write(f"DELETE FROM `{table}`;\n")

                cols_str = ", ".join([f"`{c}`" for c in cols])
                for row in rows:
                    vals = []
                    for v in row.values():
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, bool):
                            vals.append("1" if v else "0")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        else:
                            escaped = str(v).replace("'", "''")
                            vals.append(f"'{escaped}'")
                    f.write(f"INSERT INTO `{table}` ({cols_str}) VALUES ({', '.join(vals)});\n")
                f.write("\n")

            f.write("SET FOREIGN_KEY_CHECKS = 1;\n")

        cur.close()
        conn.close()
        logger.info(f"Backup MySQL: {dump_file}")
        return dump_file

    except Exception as e:
        logger.error(f"Backup MySQL falhou: {e}")
        return None


def cleanup_old_backups():
    try:
        files = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("sisgersa_") and f.endswith(".sql"):
                path = os.path.join(BACKUP_DIR, f)
                files.append((path, os.path.getmtime(path)))
        files.sort(key=lambda x: x[1], reverse=True)

        for path, _ in files[MAX_BACKUPS:]:
            os.remove(path)
            logger.info(f"Backup antigo removido: {os.path.basename(path)}")
    except Exception as e:
        logger.warning(f"Cleanup backups: {e}")


def get_last_backup():
    try:
        files = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("sisgersa_") and f.endswith(".sql"):
                path = os.path.join(BACKUP_DIR, f)
                size = os.path.getsize(path)
                mtime = os.path.getmtime(path)
                files.append({"file": os.path.basename(path), "size": size, "mtime": mtime})
        files.sort(key=lambda x: x["mtime"], reverse=True)
        return files[0] if files else None
    except Exception:
        return None


def get_backup_count():
    try:
        return len([f for f in os.listdir(BACKUP_DIR)
                     if f.startswith("sisgersa_") and f.endswith(".sql")])
    except Exception:
        return 0


_backup_thread = None
_backup_running = False


def _background_backup(interval: int = 21600):
    global _backup_running
    _backup_running = True
    logger.info(f"Backup background: intervalo={interval}s (6h)")

    while _backup_running:
        time.sleep(interval)
        if not _backup_running:
            break

        try:
            dump_file = dump_database()
            if dump_file:
                cleanup_old_backups()
        except Exception as e:
            logger.error(f"Backup background erro: {e}")


def start_background_backup(interval: int = 21600):
    global _backup_thread
    _backup_thread = threading.Thread(
        target=_background_backup,
        args=(interval,),
        daemon=True,
        name="backup-sqlite",
    )
    _backup_thread.start()
    logger.info("Background backup iniciado")


def stop_background_backup():
    global _backup_running
    _backup_running = False
    logger.info("Background backup parado")
