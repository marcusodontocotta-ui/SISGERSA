from datetime import datetime, date


def formatar_data(data) -> str:
    if isinstance(data, (datetime, date)):
        return data.strftime("%d/%m/%Y")
    return str(data)


def formatar_data_hora(dt) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y %H:%M")
    return str(dt)


def formatar_moeda(valor) -> str:
    if valor is None:
        return "-"
    return f"R$ {float(valor):,.2f}"


def pagina_atual(request, padrao=1) -> int:
    try:
        return int(request.query_params.get("page", padrao))
    except (ValueError, TypeError):
        return padrao


def registros_por_pagina(request, padrao=20) -> int:
    try:
        return int(request.query_params.get("per_page", padrao))
    except (ValueError, TypeError):
        return padrao
