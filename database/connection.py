import pymysql
from config import settings

_DB_ENGINE = settings.DB_ENGINE


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connection = None
        return cls._instance

    def _connect(self):
        try:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
        except Exception:
            pass

        if _DB_ENGINE == "postgresql":
            import psycopg
            self._connection = psycopg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                dbname=settings.DB_NAME,
                row_factory=psycopg.rows.dict_row,
                connect_timeout=10,
            )
            self._connection.autocommit = True
        else:
            self._connection = pymysql.connect(
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

    def get_connection(self):
        try:
            if self._connection is None:
                self._connect()
            elif not self._is_alive():
                self._connect()
        except Exception:
            self._connect()
        return self._connection

    def _is_alive(self):
        try:
            if self._connection is None:
                return False
            if _DB_ENGINE == "postgresql":
                return not self._connection.closed
            return self._connection.open
        except Exception:
            return False

    def execute(self, query: str, params=None):
        try:
            if not self._is_alive():
                self._connection = None
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor
        except Exception:
            self._connection = None
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor

    def fetch_one(self, query: str, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def close(self):
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None


db = Database()
