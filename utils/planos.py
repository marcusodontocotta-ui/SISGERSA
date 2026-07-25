from config import settings
from database.connection import db


def _mes_atual_filter(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if settings.DB_ENGINE == "postgresql":
        return (
            f"EXTRACT(MONTH FROM {prefix}criado_em) = EXTRACT(MONTH FROM CURRENT_DATE) "
            f"AND EXTRACT(YEAR FROM {prefix}criado_em) = EXTRACT(YEAR FROM CURRENT_DATE)"
        )
    return (
        f"MONTH({prefix}criado_em) = MONTH(CURRENT_DATE()) "
        f"AND YEAR({prefix}criado_em) = YEAR(CURRENT_DATE())"
    )


def obter_plano_estabelecimento(estabelecimento_id: int) -> dict:
    return db.fetch_one(
        """SELECT p.* FROM planos p
           JOIN estabelecimentos e ON e.plano_id = p.id
           WHERE e.id = %s""",
        (estabelecimento_id,),
    )


def contar_uso(estabelecimento_id: int) -> dict:
    consultas_mes = db.fetch_one(
        f"SELECT COUNT(*) as total FROM consultas WHERE estabelecimento_id = %s AND {_mes_atual_filter()}",
        (estabelecimento_id,),
    )
    profissionais = db.fetch_one(
        "SELECT COUNT(*) as total FROM profissional_estabelecimento WHERE estabelecimento_id = %s",
        (estabelecimento_id,),
    )
    pacientes = db.fetch_one(
        "SELECT COUNT(*) as total FROM paciente_estabelecimento WHERE estabelecimento_id = %s",
        (estabelecimento_id,),
    )
    prontuarios = db.fetch_one(
        "SELECT COUNT(*) as total FROM prontuarios WHERE estabelecimento_id = %s",
        (estabelecimento_id,),
    )
    orcamentos_mes = db.fetch_one(
        f"SELECT COUNT(*) as total FROM orcamentos WHERE estabelecimento_id = %s AND {_mes_atual_filter()}",
        (estabelecimento_id,),
    )
    procedimentos = db.fetch_one(
        "SELECT COUNT(*) as total FROM procedimentos",
        (),
    )
    return {
        "consultas_mes": consultas_mes["total"] if consultas_mes else 0,
        "profissionais": profissionais["total"] if profissionais else 0,
        "pacientes": pacientes["total"] if pacientes else 0,
        "prontuarios": prontuarios["total"] if prontuarios else 0,
        "orcamentos_mes": orcamentos_mes["total"] if orcamentos_mes else 0,
        "procedimentos": procedimentos["total"] if procedimentos else 0,
    }


def verificar_limite(estabelecimento_id, tipo_recurso: str) -> dict:
    try:
        eid = int(estabelecimento_id)
    except (TypeError, ValueError):
        return {"permitido": True, "uso": 0, "limite": -1, "plano": "Nenhum"}

    plano = obter_plano_estabelecimento(eid)
    if not plano:
        return {"permitido": True, "uso": 0, "limite": -1, "plano": "Nenhum"}

    uso = contar_uso(eid)
    valor_uso = uso.get(tipo_recurso, 0)
    limite = plano.get(f"limite_{tipo_recurso}", -1)

    if limite == -1:
        return {"permitido": True, "uso": valor_uso, "limite": -1, "plano": plano["nome"]}

    return {
        "permitido": valor_uso < limite,
        "uso": valor_uso,
        "limite": limite,
        "plano": plano["nome"],
    }


def bloquear_se_limite(estabelecimento_id, tipo_recurso: str):
    try:
        eid = int(estabelecimento_id)
    except (TypeError, ValueError):
        return
    resultado = verificar_limite(eid, tipo_recurso)
    if not resultado["permitido"]:
        plano = resultado["plano"]
        limite = resultado["limite"]
        raise LimiteAtingidoError(
            f"Limite do plano {plano} atingido: {resultado['uso']}/{limite} {tipo_recurso}. "
            f"Faça upgrade do seu plano para continuar."
        )


class LimiteAtingidoError(Exception):
    pass
