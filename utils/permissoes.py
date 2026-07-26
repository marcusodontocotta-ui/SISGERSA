from database.connection import db

MODULOS = {
    "pacientes": {"label": "Pacientes", "icon": "bi-people", "rota": "/prontuarios"},
    "consultas": {"label": "Consultas", "icon": "bi-calendar-check", "rota": "/consultas"},
    "prontuarios": {"label": "Historico", "icon": "bi-folder-medical", "rota": "/prontuarios"},
    "agenda": {"label": "Agenda", "icon": "bi-calendar-week", "rota": "/agenda"},
    "orcamentos": {"label": "Orcamentos", "icon": "bi-file-earmark-text", "rota": "/orcamentos"},
    "pagamentos": {"label": "Pagamentos", "icon": "bi-credit-card", "rota": "/pagamentos"},
    "financeiro": {"label": "Financeiro", "icon": "bi-graph-up", "rota": "/financeiro"},
    "procedimentos": {"label": "Procedimentos", "icon": "bi-clipboard2-pulse", "rota": "/procedimentos"},
    "convenios": {"label": "Convenios", "icon": "bi-shield-check", "rota": "/convenios"},
    "estabelecimentos": {"label": "Estabelecimentos", "icon": "bi-building", "rota": "/estabelecimentos"},
    "profissionais": {"label": "Profissionais", "icon": "bi-person-badge", "rota": "/profissionais"},
    "configuracoes": {"label": "Configuracoes", "icon": "bi-gear", "rota": "/configuracoes"},
}

DEFAULT_PERMISSIONS = {
    "admin": {
        "pacientes":     {"ver": True, "criar": True, "editar": True, "excluir": True},
        "consultas":     {"ver": True, "criar": True, "editar": True, "excluir": True},
        "prontuarios":   {"ver": True, "criar": True, "editar": True, "excluir": True},
        "agenda":        {"ver": True, "criar": True, "editar": True, "excluir": True},
        "orcamentos":    {"ver": True, "criar": True, "editar": True, "excluir": True},
        "pagamentos":    {"ver": True, "criar": True, "editar": True, "excluir": True},
        "financeiro":    {"ver": True, "criar": True, "editar": True, "excluir": True},
        "procedimentos": {"ver": True, "criar": True, "editar": True, "excluir": True},
        "convenios":     {"ver": True, "criar": True, "editar": True, "excluir": True},
        "estabelecimentos": {"ver": True, "criar": True, "editar": True, "excluir": True},
        "profissionais": {"ver": True, "criar": True, "editar": True, "excluir": True},
        "configuracoes": {"ver": True, "criar": True, "editar": True, "excluir": True},
    },
    "recepcionista": {
        "pacientes":     {"ver": True, "criar": True, "editar": True, "excluir": False},
        "consultas":     {"ver": True, "criar": True, "editar": True, "excluir": False},
        "prontuarios":   {"ver": True, "criar": False, "editar": False, "excluir": False},
        "agenda":        {"ver": True, "criar": True, "editar": True, "excluir": False},
        "orcamentos":    {"ver": True, "criar": True, "editar": True, "excluir": False},
        "pagamentos":    {"ver": True, "criar": True, "editar": False, "excluir": False},
        "financeiro":    {"ver": False, "criar": False, "editar": False, "excluir": False},
        "procedimentos": {"ver": True, "criar": False, "editar": False, "excluir": False},
        "convenios":     {"ver": True, "criar": False, "editar": False, "excluir": False},
        "estabelecimentos": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "profissionais": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "configuracoes": {"ver": False, "criar": False, "editar": False, "excluir": False},
    },
    "profissional": {
        "pacientes":     {"ver": True, "criar": False, "editar": False, "excluir": False},
        "consultas":     {"ver": True, "criar": False, "editar": True, "excluir": False},
        "prontuarios":   {"ver": True, "criar": True, "editar": False, "excluir": False},
        "agenda":        {"ver": True, "criar": False, "editar": False, "excluir": False},
        "orcamentos":    {"ver": True, "criar": False, "editar": False, "excluir": False},
        "pagamentos":    {"ver": False, "criar": False, "editar": False, "excluir": False},
        "financeiro":    {"ver": False, "criar": False, "editar": False, "excluir": False},
        "procedimentos": {"ver": True, "criar": False, "editar": False, "excluir": False},
        "convenios":     {"ver": False, "criar": False, "editar": False, "excluir": False},
        "estabelecimentos": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "profissionais": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "configuracoes": {"ver": False, "criar": False, "editar": False, "excluir": False},
    },
    "paciente": {
        "pacientes":     {"ver": True, "criar": False, "editar": False, "excluir": False},
        "consultas":     {"ver": True, "criar": False, "editar": False, "excluir": False},
        "prontuarios":   {"ver": True, "criar": False, "editar": False, "excluir": False},
        "agenda":        {"ver": True, "criar": False, "editar": False, "excluir": False},
        "orcamentos":    {"ver": True, "criar": False, "editar": False, "excluir": False},
        "pagamentos":    {"ver": False, "criar": False, "editar": False, "excluir": False},
        "financeiro":    {"ver": False, "criar": False, "editar": False, "excluir": False},
        "procedimentos": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "convenios":     {"ver": False, "criar": False, "editar": False, "excluir": False},
        "estabelecimentos": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "profissionais": {"ver": False, "criar": False, "editar": False, "excluir": False},
        "configuracoes": {"ver": False, "criar": False, "editar": False, "excluir": False},
    },
}

_overrides_cache = {}


def _limpar_cache(estab_id=None):
    keys = [k for k in _overrides_cache if estab_id is None or k[1] == estab_id]
    for k in keys:
        del _overrides_cache[k]


def _buscar_overrides(usuario_id: int, estabelecimento_id: int) -> dict:
    key = (usuario_id, estabelecimento_id)
    if key in _overrides_cache:
        return _overrides_cache[key]

    rows = db.fetch_all(
        "SELECT modulo, pode_ver, pode_criar, pode_editar, pode_excluir FROM permissoes_usuario WHERE usuario_id = %s AND estabelecimento_id = %s",
        (usuario_id, estabelecimento_id),
    )
    overrides = {}
    for row in rows:
        mod = row["modulo"]
        overrides[mod] = {
            "ver": bool(row["pode_ver"]) if row["pode_ver"] is not None else None,
            "criar": bool(row["pode_criar"]) if row["pode_criar"] is not None else None,
            "editar": bool(row["pode_editar"]) if row["pode_editar"] is not None else None,
            "excluir": bool(row["pode_excluir"]) if row["pode_excluir"] is not None else None,
        }
    _overrides_cache[key] = overrides
    return overrides


def pode_acessar(usuario: dict, modulo: str, acao: str = "ver", estabelecimento_id=None) -> bool:
    if usuario.get("is_super"):
        return True

    if modulo not in DEFAULT_PERMISSIONS.get(usuario["tipo"], {}):
        return False

    default = DEFAULT_PERMISSIONS[usuario["tipo"]].get(modulo, {})
    if not default.get(acao, False):
        pass

    if estabelecimento_id is None:
        estabelecimento_id = usuario.get("estabelecimento_id")

    if estabelecimento_id:
        overrides = _buscar_overrides(usuario["id"], int(estabelecimento_id))
        mod_override = overrides.get(modulo, {})
        override_val = mod_override.get(acao)
        if override_val is not None:
            return override_val

    return default.get(acao, False)


def obter_permissoes_usuario(usuario_id: int, estabelecimento_id: int) -> dict:
    rows = db.fetch_all(
        "SELECT modulo, pode_ver, pode_criar, pode_editar, pode_excluir FROM permissoes_usuario WHERE usuario_id = %s AND estabelecimento_id = %s",
        (usuario_id, estabelecimento_id),
    )
    result = {}
    for row in rows:
        result[row["modulo"]] = {
            "ver": bool(row["pode_ver"]) if row["pode_ver"] is not None else None,
            "criar": bool(row["pode_criar"]) if row["pode_criar"] is not None else None,
            "editar": bool(row["pode_editar"]) if row["pode_editar"] is not None else None,
            "excluir": bool(row["pode_excluir"]) if row["pode_excluir"] is not None else None,
        }
    return result


def salvar_permissoes(usuario_id: int, estabelecimento_id: int, permissoes: dict):
    for modulo, acoes in permissoes.items():
        db.execute(
            """INSERT INTO permissoes_usuario (usuario_id, estabelecimento_id, modulo, pode_ver, pode_criar, pode_editar, pode_excluir)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
               pode_ver = VALUES(pode_ver), pode_criar = VALUES(pode_criar),
               pode_editar = VALUES(pode_editar), pode_excluir = VALUES(pode_excluir)""",
            (
                usuario_id, estabelecimento_id, modulo,
                acoes.get("ver"), acoes.get("criar"),
                acoes.get("editar"), acoes.get("excluir"),
            ),
        )
    _limpar_cache(estabelecimento_id)


def limpar_permissoes(usuario_id: int, estabelecimento_id: int):
    db.execute(
        "DELETE FROM permissoes_usuario WHERE usuario_id = %s AND estabelecimento_id = %s",
        (usuario_id, estabelecimento_id),
    )
    _limpar_cache(estabelecimento_id)


def obter_permissoes_para_nav(usuario: dict, estabelecimento_id=None) -> dict:
    if usuario.get("is_super"):
        return {m: {"ver": True, "criar": True, "editar": True, "excluir": True} for m in MODULOS}

    if estabelecimento_id is None:
        estabelecimento_id = usuario.get("estabelecimento_id")

    resultado = {}
    for modulo in MODULOS:
        resultado[modulo] = {
            "ver": pode_acessar(usuario, modulo, "ver", estabelecimento_id),
            "criar": pode_acessar(usuario, modulo, "criar", estabelecimento_id),
            "editar": pode_acessar(usuario, modulo, "editar", estabelecimento_id),
            "excluir": pode_acessar(usuario, modulo, "excluir", estabelecimento_id),
        }
    return resultado


def exigir_permissao(usuario: dict, modulo: str, acao: str = "ver", estabelecimento_id=None):
    from fastapi import HTTPException
    if not pode_acessar(usuario, modulo, acao, estabelecimento_id):
        raise HTTPException(status_code=403, detail=f"Acesso negado ao modulo '{modulo}' ({acao})")
