import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt
from config import settings
from database.connection import db


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), hash_armazenado.encode("utf-8"))


def criar_token(usuario_id: int, tipo: str, is_super: bool = False) -> str:
    expiracao = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario_id),
        "tipo": tipo,
        "is_super": is_super,
        "exp": expiracao,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verificar_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def usuario_por_email(email: str) -> dict | None:
    return db.fetch_one("SELECT * FROM usuarios WHERE email = %s AND ativo = TRUE", (email,))


def usuarios_por_email(email: str) -> list:
    return db.fetch_all("SELECT * FROM usuarios WHERE email = %s AND ativo = TRUE ORDER BY tipo, nome", (email,))


def criar_usuario(nome: str, email: str, senha: str, tipo: str, telefone: str = None, is_super: bool = False) -> int:
    hash_pwd = hash_senha(senha)
    cursor = db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo, telefone, is_super) VALUES (%s, %s, %s, %s, %s, %s)",
        (nome, email, hash_pwd, tipo, telefone, is_super),
    )
    return cursor.lastrowid


def vincular_profissional(usuario_id: int, estabelecimento_id: int, especialidade: str = None, cargo: str = None, registro: str = None):
    db.execute(
        """INSERT INTO profissional_estabelecimento
           (usuario_id, estabelecimento_id, especialidade, cargo, registro_profissional)
           VALUES (%s, %s, %s, %s, %s)""",
        (usuario_id, estabelecimento_id, especialidade, cargo, registro),
    )


def vincular_paciente(usuario_id: int, estabelecimento_id: int, observacoes: str = None):
    db.execute(
        "INSERT INTO paciente_estabelecimento (usuario_id, estabelecimento_id, observacoes) VALUES (%s, %s, %s)",
        (usuario_id, estabelecimento_id, observacoes),
    )


def obter_estabelecimentos_usuario(usuario_id: int) -> list:
    return db.fetch_all(
        """SELECT e.*, pe.especialidade, pe.cargo
           FROM estabelecimentos e
           JOIN profissional_estabelecimento pe ON pe.estabelecimento_id = e.id
           WHERE pe.usuario_id = %s AND e.ativo = TRUE""",
        (usuario_id,),
    )


def obter_permissoes_paciente(usuario_id: int, estabelecimento_id: int) -> list:
    return db.fetch_all(
        "SELECT * FROM permissoes_paciente WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
        (usuario_id, estabelecimento_id),
    )


def definir_permisao_paciente(usuario_id: int, estabelecimento_id: int, modulo: str, pode_ver: bool = False, pode_criar: bool = False, pode_editar: bool = False, pode_excluir: bool = False):
    db.execute(
        """INSERT INTO permissoes_paciente
           (estabelecimento_id, paciente_usuario_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
           pode_ver = VALUES(pode_ver), pode_criar = VALUES(pode_criar),
           pode_editar = VALUES(pode_editar), pode_excluir = VALUES(pode_excluir)""",
        (estabelecimento_id, usuario_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir),
    )
