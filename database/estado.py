import json
import logging
from datetime import datetime, timedelta

from config import settings
from database.connection import db

logger = logging.getLogger("estado")
_ENGINE = settings.DB_ENGINE


def _upsert_contador(chave: str, janela_segundos: int) -> int:
    """Incrementa o contador de `chave` dentro da janela; retorna a contagem atual."""
    agora = datetime.now()
    inicio = agora - timedelta(seconds=janela_segundos)
    if _ENGINE == "postgresql":
        row = db.fetch_one(
            """INSERT INTO rate_limits (chave, contagem, janela_inicio)
               VALUES (%s, 1, %s)
               ON CONFLICT (chave) DO UPDATE SET
                 contagem = CASE WHEN rate_limits.janela_inicio < %s THEN 1 ELSE rate_limits.contagem + 1 END,
                 janela_inicio = CASE WHEN rate_limits.janela_inicio < %s THEN %s ELSE rate_limits.janela_inicio END
               RETURNING contagem""",
            (chave, agora, inicio, inicio, agora),
        )
        return int(row["contagem"])
    db.execute(
        """INSERT INTO rate_limits (chave, contagem, janela_inicio) VALUES (%s, 1, %s)
           ON DUPLICATE KEY UPDATE
             contagem = IF(janela_inicio < %s, 1, contagem + 1),
             janela_inicio = IF(janela_inicio < %s, %s, janela_inicio)""",
        (chave, agora, inicio, inicio, agora),
    )
    row = db.fetch_one("SELECT contagem FROM rate_limits WHERE chave = %s", (chave,))
    return int(row["contagem"]) if row else 1


def rate_limit_excedido(chave: str, janela_segundos: int, limite: int) -> bool:
    row = db.fetch_one(
        "SELECT contagem FROM rate_limits WHERE chave = %s AND janela_inicio >= %s",
        (chave, datetime.now() - timedelta(seconds=janela_segundos)),
    )
    return bool(row) and int(row["contagem"]) >= limite


def registrar_tentativa(chave: str, janela_segundos: int):
    _upsert_contador(chave, janela_segundos)


def incrementar_contador(chave: str, janela_segundos: int) -> int:
    return _upsert_contador(chave, janela_segundos)


def criar_pending_login(session_key: str, user_ids):
    db.execute("DELETE FROM pending_logins WHERE session_key = %s", (session_key,))
    db.execute(
        "INSERT INTO pending_logins (session_key, user_ids) VALUES (%s, %s)",
        (session_key, json.dumps([int(i) for i in user_ids])),
    )


def consumir_pending_login(session_key: str) -> list:
    row = db.fetch_one(
        "SELECT user_ids FROM pending_logins WHERE session_key = %s", (session_key,)
    )
    db.execute("DELETE FROM pending_logins WHERE session_key = %s", (session_key,))
    if not row or not row.get("user_ids"):
        return []
    try:
        return json.loads(row["user_ids"])
    except Exception:
        return []


def limpar_estado_antigo():
    agora = datetime.now()
    db.execute(
        "DELETE FROM rate_limits WHERE janela_inicio < %s",
        (agora - timedelta(seconds=1800),),
    )
    db.execute(
        "DELETE FROM pending_logins WHERE criado_em < %s",
        (agora - timedelta(hours=24),),
    )
