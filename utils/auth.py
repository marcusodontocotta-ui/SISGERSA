import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt
from config import settings
from database.connection import db

_ENGINE = settings.DB_ENGINE


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


def _resolver_tipo_profissional(row: dict) -> str:
    if row.get("is_admin_geral") or row.get("is_admin_estabelecimento"):
        return "admin"
    if row.get("is_recepcionista"):
        return "recepcionista"
    return "profissional"


def _normalizar_usuario(row: dict, tabela: str) -> dict | None:
    if not row:
        return None
    row = dict(row)
    if tabela == "pacientes":
        row["tipo"] = "paciente"
    elif tabela == "profissionais":
        row["tipo"] = _resolver_tipo_profissional(row)
    return row


def usuario_por_email(email: str) -> dict | None:
    return db.fetch_one(
        "SELECT * FROM usuarios WHERE email = %s AND ativo = TRUE", (email,)
    )


def usuarios_por_email(email: str) -> list:
    return db.fetch_all(
        "SELECT * FROM usuarios WHERE email = %s AND ativo = TRUE ORDER BY tipo, nome", (email,)
    )


def _normalizar_cpf(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _is_cpf(texto: str) -> bool:
    cpf = _normalizar_cpf(texto)
    return len(cpf) == 11 and cpf.isdigit()


def _filtro_cpf_limpo(coluna: str = "cpf") -> str:
    if _ENGINE == "postgresql":
        return f"REGEXP_REPLACE({coluna}, '[^0-9]', '', 'g')"
    return f"REPLACE(REPLACE(REPLACE({coluna}, '.', ''), '-', ''), ' ', '')"


def usuarios_por_cpf(cpf: str) -> list:
    cpf_limpo = _normalizar_cpf(cpf)
    filtro = _filtro_cpf_limpo()
    return db.fetch_all(
        f"SELECT * FROM usuarios WHERE {filtro} = %s AND ativo = TRUE ORDER BY tipo, nome",
        (cpf_limpo,),
    )


def usuario_por_cpf(cpf: str) -> dict | None:
    cpf_limpo = _normalizar_cpf(cpf)
    filtro = _filtro_cpf_limpo()
    return db.fetch_one(
        f"SELECT * FROM usuarios WHERE {filtro} = %s AND ativo = TRUE",
        (cpf_limpo,),
    )


def criar_usuario(nome: str, email: str, senha: str, tipo: str, telefone: str = None, is_super: bool = False) -> int:
    hash_pwd = hash_senha(senha)
    cursor = db.execute(
        """INSERT INTO usuarios (nome, email, senha_hash, tipo, is_super, telefone, ativo)
           VALUES (%s, %s, %s, %s, %s, %s, TRUE)""",
        (nome, email, hash_pwd, tipo, is_super, telefone),
    )
    return cursor.lastrowid


def criar_paciente(
    nome: str, email: str, senha: str, telefone: str = None,
    cpf: str = None, data_nascimento: str = None, tipo_pagamento: str = "particular",
) -> int:
    user_id = criar_usuario(nome=nome, email=email, senha=senha, tipo="paciente", telefone=telefone)
    if cpf or data_nascimento:
        db.execute(
            "UPDATE usuarios SET cpf = %s, data_nascimento = %s WHERE id = %s",
            (cpf, data_nascimento, user_id),
        )
    return user_id


def criar_profissional(
    nome: str, email: str, senha: str, telefone: str = None,
    is_dentista: bool = False, is_medico: bool = False, is_enfermeiro: bool = False,
    is_admin_geral: bool = False, is_admin_estabelecimento: bool = False,
    is_recepcionista: bool = False, is_super: bool = False,
) -> int:
    if is_admin_geral or is_admin_estabelecimento:
        tipo = "admin"
    elif is_recepcionista:
        tipo = "recepcionista"
    else:
        tipo = "profissional"
    return criar_usuario(nome=nome, email=email, senha=senha, tipo=tipo, telefone=telefone, is_super=is_super)


def vincular_profissional(usuario_id: int, estabelecimento_id: int, especialidade: str = None, cargo: str = None, registro: str = None):
    if _ENGINE == "postgresql":
        db.execute(
            """INSERT INTO profissional_estabelecimento
               (usuario_id, estabelecimento_id, especialidade, cargo, registro_profissional)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (usuario_id, estabelecimento_id, especialidade, cargo, registro),
        )
    else:
        db.execute(
            """INSERT IGNORE INTO profissional_estabelecimento
               (usuario_id, estabelecimento_id, especialidade, cargo, registro_profissional)
               VALUES (%s, %s, %s, %s, %s)""",
            (usuario_id, estabelecimento_id, especialidade, cargo, registro),
        )


def vincular_paciente(usuario_id: int, estabelecimento_id: int, observacoes: str = None):
    if _ENGINE == "postgresql":
        db.execute(
            """INSERT INTO paciente_estabelecimento (usuario_id, estabelecimento_id, observacoes)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (usuario_id, estabelecimento_id, observacoes),
        )
    else:
        db.execute(
            """INSERT IGNORE INTO paciente_estabelecimento (usuario_id, estabelecimento_id, observacoes)
               VALUES (%s, %s, %s)""",
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
    if _ENGINE == "postgresql":
        db.execute(
            """INSERT INTO permissoes_paciente
               (estabelecimento_id, paciente_usuario_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (estabelecimento_id, paciente_usuario_id, modulo) DO UPDATE SET
               pode_ver = EXCLUDED.pode_ver, pode_criar = EXCLUDED.pode_criar,
               pode_editar = EXCLUDED.pode_editar, pode_excluir = EXCLUDED.pode_excluir""",
            (estabelecimento_id, usuario_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir),
        )
    else:
        db.execute(
            """INSERT INTO permissoes_paciente
               (estabelecimento_id, paciente_usuario_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
               pode_ver = VALUES(pode_ver), pode_criar = VALUES(pode_criar),
               pode_editar = VALUES(pode_editar), pode_excluir = VALUES(pode_excluir)""",
            (estabelecimento_id, usuario_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir),
        )
