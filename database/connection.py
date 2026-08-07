import threading
import logging
import time
from contextlib import contextmanager

from config import settings

_DB_ENGINE = settings.DB_ENGINE
logger = logging.getLogger("database")

MAX_CONNECTIONS = max(2, settings.DB_MAX_CONNECTIONS)
EVICT_IDLE_SECONDS = 30


class Database:
    """Singleton de acesso ao banco com pool de conexoes por thread.

    Cada thread (requisicao, scheduler, cache, backup) ganha a propria
    conexao, evitando o uso concorrente de uma unica conexao (race condition
    com pymysql/psycopg). O pool e limitado por MAX_CONNECTIONS; conexoes
    ociosas sao fechadas quando o limite e atingido.

    O modo padrao continua sendo autocommit=True (nenhum comportamento
    existente muda). Transacoes explicitas podem ser usadas via
    db.transaction() (commit no sucesso / rollback na excecao).
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connections = {}
            cls._instance._last_used = {}
            cls._instance._lock = threading.RLock()
            cls._instance._local = threading.local()
        return cls._instance

    # ---------- conexao ----------
    def _create_connection(self):
        if _DB_ENGINE == "postgresql":
            import psycopg
            conn = psycopg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                dbname=settings.DB_NAME,
                row_factory=psycopg.rows.dict_row,
                connect_timeout=10,
                sslmode="prefer",
            )
            conn.autocommit = True
            return conn
        import pymysql
        return pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )

    def _is_alive(self, conn) -> bool:
        try:
            if _DB_ENGINE == "postgresql":
                return not conn.closed
            conn.ping(reconnect=True)
            return True
        except Exception:
            return False

    def _touch(self, ident=None):
        self._last_used[ident or self._ident()] = time.time()

    def _ident(self):
        return threading.get_ident()

    def _discard(self, ident=None):
        ident = ident or self._ident()
        conn = self._connections.pop(ident, None)
        self._last_used.pop(ident, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _evict_if_needed(self):
        now = time.time()
        if len(self._connections) < MAX_CONNECTIONS:
            return
        idle = [
            ident
            for ident, ts in self._last_used.items()
            if now - ts > EVICT_IDLE_SECONDS
        ]
        idle.sort(key=lambda ident: self._last_used[ident])
        while idle and len(self._connections) >= MAX_CONNECTIONS:
            self._discard(idle.pop(0))
        if len(self._connections) >= MAX_CONNECTIONS * 2:
            oldest = sorted(self._last_used.items(), key=lambda kv: kv[1])[0][0]
            self._discard(oldest)

    def get_connection(self):
        with self._lock:
            ident = self._ident()
            conn = getattr(self._local, "connection", None)
            if conn is None:
                self._evict_if_needed()
                conn = self._connections.get(ident)
                if conn is None:
                    conn = self._create_connection()
                    self._connections[ident] = conn
                self._local.connection = conn
            elif not self._is_alive(conn):
                self._discard(ident)
                self._local.connection = None
                self._evict_if_needed()
                conn = self._create_connection()
                self._connections[ident] = conn
                self._local.connection = conn
            self._touch(ident)
            return conn

    def ping(self) -> bool:
        with self._lock:
            try:
                conn = self.get_connection()
                if _DB_ENGINE == "postgresql":
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
                else:
                    conn.ping(reconnect=True)
                return True
            except Exception:
                try:
                    self._discard(self._ident())
                except Exception:
                    pass
                return False

    def execute(self, query: str, params=None):
        with self._lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute(query, params)
                self._touch()
                return cursor
            except Exception:
                self._discard(self._ident())
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute(query, params)
                self._touch()
                return cursor

    def fetch_one(self, query: str, params=None):
        with self._lock:
            cursor = self.execute(query, params)
            row = cursor.fetchone()
            if row is not None and _DB_ENGINE == "postgresql":
                return dict(row)
            return row

    def fetch_all(self, query: str, params=None):
        with self._lock:
            cursor = self.execute(query, params)
            rows = cursor.fetchall()
            if _DB_ENGINE == "postgresql":
                return [dict(r) for r in rows]
            return rows

    def close(self):
        with self._lock:
            for ident in list(self._connections.keys()):
                self._discard(ident)
            try:
                self._local.connection = None
            except Exception:
                pass

    # ---------- transacoes ----------
    @contextmanager
    def transaction(self):
        conn = self.get_connection()
        prev = self._get_autocommit(conn)
        self._set_autocommit(conn, False)
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self._set_autocommit(conn, prev)

    def _get_autocommit(self, conn) -> bool:
        try:
            if _DB_ENGINE == "postgresql":
                return bool(conn.autocommit)
            return bool(conn.get_autocommit())
        except Exception:
            return True

    def _set_autocommit(self, conn, value: bool):
        try:
            if _DB_ENGINE == "postgresql":
                conn.autocommit = value
            else:
                conn.autocommit(value)
        except Exception:
            pass


db = Database()
