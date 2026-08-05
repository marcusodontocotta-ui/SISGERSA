from database.connection import db
import unicodedata

TIPO_CONTRA = {
    "alergia": "Alergia",
    "gestacao": "Gravidez",
    "condicao": "Condição clínica",
}


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def _chaves_descricao(descricao, tipo):
    chaves = [w.strip() for w in descricao.split(",") if w.strip()]
    if tipo == "alergia":
        for pref in ("alergia a ", "alergia a", "hipersensibilidade a ", "hipersensibilidade a", "hipersensibilidade à ", "hipersensibilidade à"):
            reduzido = [c for c in chaves if c != pref]
            if reduzido != chaves:
                chaves = reduzido
                break
        nova = []
        for c in chaves:
            c = _normalizar(c)
            for pref in ("alergia a ", "alergia a", "hipersensibilidade a ", "hipersensibilidade à "):
                if c.startswith(pref):
                    c = c[len(pref):].strip()
            nova.append(c)
        chaves = nova
    else:
        chaves = [_normalizar(c) for c in chaves]
    return chaves


def _texto_casa(texto_paciente, chaves):
    tp = _normalizar(texto_paciente)
    for ch in chaves:
        if not ch:
            continue
        if ch in tp or tp in ch:
            return True
    return False


def resolver_principios_medicamento(medicamento_id=None, nome_medicamento=None):
    pa_ids = set()

    if medicamento_id:
        rows = db.fetch_all(
            "SELECT principio_ativo_id FROM medicamento_principios WHERE medicamento_id = %s",
            (medicamento_id,),
        )
        pa_ids.update(r["principio_ativo_id"] for r in rows)

    if nome_medicamento:
        rows = db.fetch_all(
            "SELECT m.id FROM medicamentos m WHERE LOWER(m.nome) = LOWER(%s) LIMIT 1",
            (nome_medicamento,),
        )
        if not rows:
            rows = db.fetch_all(
                "SELECT m.id FROM medicamentos m WHERE LOWER(m.principio_ativo) = LOWER(%s) LIMIT 1",
                (nome_medicamento,),
            )
        if rows:
            med = db.fetch_all(
                "SELECT principio_ativo_id FROM medicamento_principios WHERE medicamento_id = %s",
                (rows[0]["id"],),
            )
            pa_ids.update(r["principio_ativo_id"] for r in med)

    return pa_ids


def expandir_sinonimos(pa_ids):
    if not pa_ids:
        return set()
    ids = list(pa_ids)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"SELECT sinonimo_id, canonico_id FROM principio_sinonimos WHERE sinonimo_id IN ({placeholders})",
        ids,
    )
    expandido = set(ids)
    for r in rows:
        expandido.add(r["canonico_id"])
    return expandido


def principios_curados(pa_ids):
    pa_ids = expandir_sinonimos(pa_ids)
    if not pa_ids:
        return []
    ids = list(pa_ids)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"""SELECT DISTINCT p.id, p.nome
            FROM principios_ativos p
            WHERE p.id IN ({placeholders})
              AND (EXISTS (SELECT 1 FROM indicacoes i WHERE i.principio_ativo_id = p.id)
                OR EXISTS (SELECT 1 FROM efeitos_colaterais e WHERE e.principio_ativo_id = p.id)
                OR EXISTS (SELECT 1 FROM interacoes_medicamentosas im WHERE im.medicamento_a_id = p.id OR im.medicamento_b_id = p.id)
                OR EXISTS (SELECT 1 FROM contra_indicacoes ci WHERE ci.principio_ativo_id = p.id))
            ORDER BY p.nome""",
        ids,
    )
    return rows


def medicamentos_ativos_paciente(paciente_id):
    return db.fetch_all(
        """SELECT pm.id, pm.medicamento_id, pm.nome_medicamento
           FROM paciente_medicamentos pm
           WHERE pm.paciente_id = %s AND pm.ativo = TRUE
           ORDER BY pm.criado_em DESC""",
        (paciente_id,),
    )


def checar_interacoes(paciente_id, pa_ids_novos):
    pa_ids_novos = expandir_sinonimos(pa_ids_novos)
    if not pa_ids_novos:
        return []

    ativos = medicamentos_ativos_paciente(paciente_id)
    pa_ativos = set()
    for med in ativos:
        pa_ativos |= resolver_principios_medicamento(med["medicamento_id"], med["nome_medicamento"])
    pa_ativos = expandir_sinonimos(pa_ativos)

    alertas = []
    pa_novos = pa_ids_novos - pa_ativos
    if not pa_novos:
        return []

    ids_novos = list(pa_novos)
    ids_ativos = list(pa_ativos)
    if not ids_ativos:
        return []

    pn = ",".join(["%s"] * len(ids_novos))
    pa = ",".join(["%s"] * len(ids_ativos))
    rows = db.fetch_all(
        f"""SELECT a.nome AS pa_a, b.nome AS pa_b, i.severidade, i.descricao, i.conduta
            FROM interacoes_medicamentosas i
            JOIN principios_ativos a ON a.id = i.medicamento_a_id
            JOIN principios_ativos b ON b.id = i.medicamento_b_id
            WHERE (i.medicamento_a_id IN ({pn}) AND i.medicamento_b_id IN ({pa}))
               OR (i.medicamento_a_id IN ({pa}) AND i.medicamento_b_id IN ({pn}))
            ORDER BY CASE i.severidade WHEN 'grave' THEN 1 WHEN 'moderada' THEN 2 ELSE 3 END""",
        ids_novos + ids_ativos + ids_ativos + ids_novos,
    )

    for r in rows:
        alertas.append({
            "tipo": "interacao",
            "severidade": r["severidade"],
            "mensagem": f"{r['pa_a']} + {r['pa_b']}: {r['descricao']}",
            "conduta": r["conduta"],
        })
    return alertas


def checar_contra_indicacoes(paciente_id, pa_ids_novos):
    pa_ids_novos = expandir_sinonimos(pa_ids_novos)
    if not pa_ids_novos:
        return []

    anamnese = db.fetch_one(
        "SELECT alergias, gestante, historico_medico FROM anamnese WHERE paciente_id = %s ORDER BY criado_em DESC LIMIT 1",
        (paciente_id,),
    )
    alertas = []

    texto_alergias = (anamnese["alergias"] or "").lower() if anamnese else ""
    gestante = bool(anamnese["gestante"]) if anamnese else False
    texto_condicoes = (anamnese["historico_medico"] or "").lower() if anamnese else ""

    ids = list(pa_ids_novos)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"""SELECT p.nome AS pa, c.tipo, c.descricao, c.severidade
            FROM contra_indicacoes c
            JOIN principios_ativos p ON p.id = c.principio_ativo_id
            WHERE c.principio_ativo_id IN ({placeholders})
            ORDER BY CASE c.severidade WHEN 'grave' THEN 1 WHEN 'moderada' THEN 2 ELSE 3 END""",
        ids,
    )

    for r in rows:
        desc = r["descricao"].lower()
        tipo = r["tipo"]

        if tipo == "alergia":
            chaves = _chaves_descricao(desc, tipo)
            if _texto_casa(texto_alergias, chaves):
                alertas.append({
                    "tipo": "contraindicacao",
                    "severidade": r["severidade"],
                    "mensagem": f"{r['pa']}: alergia registrada na anamnese ({desc}).",
                })
        elif tipo == "gestacao":
            if gestante:
                alertas.append({
                    "tipo": "contraindicacao",
                    "severidade": r["severidade"],
                    "mensagem": f"{r['pa']}: contra-indicado na gravidez ({desc}).",
                })
        elif tipo == "condicao":
            chaves = _chaves_descricao(desc, tipo)
            if _texto_casa(texto_condicoes, chaves):
                alertas.append({
                    "tipo": "contraindicacao",
                    "severidade": r["severidade"],
                    "mensagem": f"{r['pa']}: condição clínica compatível registrada ({desc}).",
                })

    return alertas


def checar_medicamento_paciente(paciente_id, medicamento_id=None, nome_medicamento=None):
    pa_ids = resolver_principios_medicamento(medicamento_id, nome_medicamento)
    alertas = []
    alertas += checar_interacoes(paciente_id, pa_ids)
    alertas += checar_contra_indicacoes(paciente_id, pa_ids)
    return alertas


def sugestoes_para_sintoma(sintoma_nome):
    rows = db.fetch_all(
        """SELECT p.nome, p.posologia, i.linha_tratamento, i.eficacia, s.nome AS sintoma
           FROM indicacoes i
           JOIN principios_ativos p ON p.id = i.principio_ativo_id
           JOIN sintomas s ON s.id = i.sintoma_id
           WHERE LOWER(s.nome) = LOWER(%s)
           ORDER BY i.linha_tratamento, i.eficacia DESC""",
        (sintoma_nome,),
    )
    return rows
