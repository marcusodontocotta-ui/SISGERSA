import socket
import time
import threading
import logging

logger = logging.getLogger("connectivity")


class ConnectivityChecker:
    def __init__(self, host: str, port: int, timeout: int = 5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._is_online = True
        self._lock = threading.Lock()
        self._last_check = 0.0
        self._check_interval = 10

    def is_online(self) -> bool:
        now = time.time()
        if now - self._last_check < self._check_interval:
            return self._is_online
        return self.check_now()

    def check_now(self) -> bool:
        try:
            import psycopg
            from config import settings
            conn = psycopg.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                dbname=settings.DB_NAME,
                connect_timeout=5,
                sslmode="prefer",
            )
            conn.close()
            online = True
        except Exception:
            online = False

        with self._lock:
            was_online = self._is_online
            self._is_online = online
            self._last_check = time.time()

        if was_online and not online:
            logger.warning("Conexao perdida com Render PostgreSQL")
        elif not was_online and online:
            logger.info("Conexao restaurada com Render PostgreSQL")

        return online

    def force_check(self) -> bool:
        return self.check_now()


_checker = None


def init_connectivity_checker(host: str, port: int):
    global _checker
    _checker = ConnectivityChecker(host, port)
    logger.info(f"ConnectivityChecker: {host}:{port}")
    return _checker


def is_online() -> bool:
    if _checker is None:
        return True
    return _checker.is_online()


def force_check() -> bool:
    if _checker is None:
        return True
    return _checker.force_check()
