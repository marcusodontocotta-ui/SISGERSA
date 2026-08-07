from database.connection import db
import re
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


_RE_NAO_PALAVRA = re.compile(r"[a-z0-9]")

# Sinônimos/variantes de termos clínicos para o histórico médico (condições).
# Chaves normalizadas (minúsculas, sem acento) -> variações que também casam.
SINONIMOS_CONDICAO = {
    "colite associada a antibiotico previa": [
        "colite", "colite associada a antibiotico", "colite pseudomembranosa",
        "diarreia por antibiotico",
    ],
    "criancas < 8 anos (mancha dentaria)": [
        "crianca", "criancas", "menor de 8 anos", "menor de oito anos",
    ],
    "diabetes descompensado (uso prolongado)": [
        "diabetes", "diabetes mellitus", "diabetico", "dm",
    ],
    "discrasias sanguineas": [
        "discrasia", "discrasias", "discrasia sanguinea", "hemofilia", "hemofilico",
        "coagulopatia", "coagulopatias", "plaquetopenia", "trombocitopenia",
        "leucopenia", "purpura", "doenca hematologica", "doencas hematologicas",
    ],
    "doenca cardiaca isquemica/icc": [
        "doenca cardiaca", "doenca cardiaca isquemica", "insuficiencia cardiaca",
        "icc", "cardiaco", "coronariopatia", "angina", "infarto",
    ],
    "doenca hepatica grave": [
        "doenca hepatica", "hepatopatia", "cirrose", "doenca do figado", "hepatite",
    ],
    "hepatopatia ativa": ["hepatopatia", "hepatopatia ativa", "doenca hepatica", "hepatite", "cirrose"],
    "hepatopatia previa": ["hepatopatia previa", "hepatopatia", "doenca hepatica previa"],
    "infeccao fungica sistemica nao tratada": [
        "infeccao fungica", "micose sistemica", "candidemia", "aspergilose", "fungemia",
    ],
    "infeccao sistemica nao tratada": [
        "infeccao sistemica", "infeccao", "sepse", "bacteremia", "septicemia",
    ],
    "ingestao de alcool (reacao dissulfiram-like)": [
        "alcool", "alcoolismo", "etilismo", "ingestao de alcool",
    ],
    "insuficiencia hepatica grave": [
        "insuficiencia hepatica", "insuficiencia hepatica cronica", "doenca hepatica",
        "falencia hepatica", "cirrose", "hepatopatia",
    ],
    "insuficiencia renal grave": [
        "insuficiencia renal", "insuficiencia renal cronica", "doenca renal",
        "doenca renal cronica", "nefropatia", "nefropatia diabetica",
        "doenca renal diabetica", "falencia renal", "dialise", "insuficiencia renal aguda",
    ],
    "ulcera peptica ativa": [
        "ulcera", "ulcera peptica", "ulcera gastrica", "ulcera duodenal",
        "gastrite", "dispepsia",
    ],
    "uso concomitante de farmacos com interacao qt": [
        "interacao qt", "prolongamento qt", "intervalo qt", "qt longo",
        "sindrome do qt longo", "torcades", "qtc", "qt",
    ],
}


def _variacoes_condicao(chaves):
    extras = set()
    for ch in chaves:
        for termo, variacoes in SINONIMOS_CONDICAO.items():
            if ch == termo or termo in ch or ch in termo:
                extras.update(variacoes)
                break
    return sorted(extras)


def _tem_fronteira(pedaco, alvo):
    """True se `pedaco` ocorre em `alvo` delimitado por caracteres não
    alfanuméricos (fronteira de palavra), evitando falsos positivos de
    substring, ex: 'sulfa' em 'sulfato ferroso'."""
    if not pedaco:
        return False
    for pos in [m.start() for m in re.finditer(re.escape(pedaco), alvo)]:
        ant = alvo[pos - 1] if pos > 0 else ""
        pos2 = pos + len(pedaco)
        prox = alvo[pos2] if pos2 < len(alvo) else ""
        if not (_RE_NAO_PALAVRA.search(ant) or _RE_NAO_PALAVRA.search(prox)):
            return True
    return False


def _texto_casa(texto_paciente, chaves):
    tp = _normalizar(texto_paciente or "")
    if not tp or not chaves:
        return False
    for ch in chaves:
        if not ch:
            continue
        if _tem_fronteira(ch, tp) or _tem_fronteira(tp, ch):
            return True
        for v in _variantes_plural(ch):
            if v and (_tem_fronteira(v, tp) or _tem_fronteira(tp, v)):
                return True
    return False


def _variantes_plural(palavra):
    """Gera variantes singular/plural básicas de português para palavras simples."""
    v = {palavra}
    p = palavra.lower()
    if p.endswith("ns") and len(p) > 3:
        v.add(p[:-2] + "m")
    elif p.endswith("oes") and len(p) > 4:
        v.add(p[:-3] + "ao")
    elif p.endswith("aes") and len(p) > 4:
        v.add(p[:-3] + "ao")
    elif p.endswith("ais") and len(p) > 4:
        v.add(p[:-3] + "al")
    elif p.endswith("eis") and len(p) > 4:
        v.add(p[:-3] + "el")
    elif p.endswith("s") and len(p) > 3:
        v.add(p[:-1])
    if not p.endswith("s"):
        if p.endswith("al") and len(p) > 3:
            v.add(p[:-2] + "ais")
        elif p.endswith("el") and len(p) > 3:
            v.add(p[:-2] + "eis")
        elif p.endswith("ol") and len(p) > 3:
            v.add(p[:-2] + "ois")
        elif p.endswith("ao") and len(p) > 3:
            v.add(p[:-2] + "oes")
        else:
            v.add(p + "s")
    return v


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
        if not pa_ids:
            rows = db.fetch_all(
                """SELECT ps.canonico_id
                   FROM principio_sinonimos ps
                   JOIN principios_ativos s ON s.id = ps.sinonimo_id
                   WHERE LOWER(s.nome) = LOWER(%s) LIMIT 1""",
                (nome_medicamento,),
            )
            if rows:
                pa_ids.update(r["canonico_id"] for r in rows)
            else:
                rows = db.fetch_all(
                    "SELECT id FROM principios_ativos WHERE LOWER(nome) = LOWER(%s) LIMIT 1",
                    (nome_medicamento,),
                )
                pa_ids.update(r["id"] for r in rows)

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
    mapa = {r["sinonimo_id"]: r["canonico_id"] for r in rows}
    if not mapa:
        return set(ids)
    return {mapa.get(pid, pid) for pid in ids}


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
            "pa": r["pa_a"],
            "pa_b": r["pa_b"],
        })
    return alertas


def _chaves_classes(pa_ids):
    """Retorna {pa_id: {chaves de classe}} - nomes das classes e de todos os
    membros de cada classe dos PAs, normalizados (matching por classe)."""
    if not pa_ids:
        return {}
    ids = list(pa_ids)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"""SELECT cpa.principio_ativo_id AS pa_id,
                   cl.nome AS classe,
                   m.nome AS membro,
                   s.nome AS sinonimo
            FROM classe_principio_ativo cpa
            JOIN classes_farmacologicas cl ON cl.id = cpa.classe_id
            LEFT JOIN classe_principio_ativo cpa_m ON cpa_m.classe_id = cl.id
            LEFT JOIN principios_ativos m ON m.id = cpa_m.principio_ativo_id
            LEFT JOIN principio_sinonimos ps ON ps.canonico_id = m.id
            LEFT JOIN principios_ativos s ON s.id = ps.sinonimo_id
            WHERE cpa.principio_ativo_id IN ({placeholders})""",
        ids,
    )
    mapa = {}
    for r in rows:
        chaves = mapa.setdefault(r["pa_id"], set())
        if r["classe"]:
            chaves.add(_normalizar(r["classe"]))
        if r["membro"]:
            chaves.add(_normalizar(r["membro"]))
        if r["sinonimo"]:
            chaves.add(_normalizar(r["sinonimo"]))
    return mapa


def _chaves_sinonimos(pa_ids):
    """Retorna {pa_id: {chaves}} com os nomes dos sinônimos do princípio ativo
    canônico (ex: canonico paracetamol -> sinonimo tylenol)."""
    if not pa_ids:
        return {}
    ids = list(pa_ids)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"""SELECT ps.canonico_id AS pa_id, s.nome AS sinonimo
            FROM principio_sinonimos ps
            JOIN principios_ativos s ON s.id = ps.sinonimo_id
            WHERE ps.canonico_id IN ({placeholders})""",
        ids,
    )
    mapa = {}
    for r in rows:
        if r["sinonimo"]:
            mapa.setdefault(r["pa_id"], set()).add(_normalizar(r["sinonimo"]))
    return mapa


def _chaves_cruzadas(pa_ids):
    """Retorna {pa_id: {chaves}} de reações cruzadas: para cada PA prescrito,
    as chaves (nomes/membros/sinônimos) das classes que reagem de forma cruzada
    com as classes do PA. Ex: cefalexina (Cefalosporinas) ganha as chaves de
    Penicilinas, detectando paciente alérgico a penicilinas."""
    if not pa_ids:
        return {}
    ids = list(pa_ids)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"""SELECT cpa.principio_ativo_id AS pa_id,
                   cl_o.nome AS classe,
                   m.nome AS membro,
                   s.nome AS sinonimo,
                   rc.descricao,
                   rc.severidade
            FROM classe_principio_ativo cpa
            JOIN reacoes_cruzadas rc ON rc.classe_alvo_id = cpa.classe_id
            JOIN classes_farmacologicas cl_o ON cl_o.id = rc.classe_origem_id
            LEFT JOIN classe_principio_ativo cpa_m ON cpa_m.classe_id = cl_o.id
            LEFT JOIN principios_ativos m ON m.id = cpa_m.principio_ativo_id
            LEFT JOIN principio_sinonimos ps ON ps.canonico_id = m.id
            LEFT JOIN principios_ativos s ON s.id = ps.sinonimo_id
            WHERE cpa.principio_ativo_id IN ({placeholders})""",
        ids,
    )
    mapa = {}
    info = {}
    for r in rows:
        chaves = mapa.setdefault(r["pa_id"], set())
        if r["classe"]:
            chaves.add(_normalizar(r["classe"]))
        if r["membro"]:
            chaves.add(_normalizar(r["membro"]))
        if r["sinonimo"]:
            chaves.add(_normalizar(r["sinonimo"]))
        if r["descricao"]:
            info.setdefault(r["pa_id"], set()).add((r["severidade"], r["descricao"]))
    return mapa, info


def _classes_por_pa(pa_ids):
    """Retorna {pa_id: [nomes das classes do PA]} para exibição no alerta."""
    if not pa_ids:
        return {}
    ids = list(pa_ids)
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"""SELECT DISTINCT cpa.principio_ativo_id AS pa_id, cl.nome AS classe
            FROM classe_principio_ativo cpa
            JOIN classes_farmacologicas cl ON cl.id = cpa.classe_id
            WHERE cpa.principio_ativo_id IN ({placeholders})
            ORDER BY cl.nome""",
        ids,
    )
    mapa = {}
    for r in rows:
        mapa.setdefault(r["pa_id"], []).append(r["classe"])
    return mapa


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
        f"""SELECT p.nome AS pa, p.id AS pa_id, c.tipo, c.descricao, c.severidade
            FROM contra_indicacoes c
            JOIN principios_ativos p ON p.id = c.principio_ativo_id
            WHERE c.principio_ativo_id IN ({placeholders})
            ORDER BY CASE c.severidade WHEN 'grave' THEN 1 WHEN 'moderada' THEN 2 ELSE 3 END""",
        ids,
    )

    chaves_classes = _chaves_classes(pa_ids_novos)
    chaves_sinonimos = _chaves_sinonimos(pa_ids_novos)
    chaves_cruzadas, info_cruzadas = _chaves_cruzadas(pa_ids_novos)
    classes_por_pa = _classes_por_pa(pa_ids_novos)

    for r in rows:
        desc = r["descricao"].lower()
        tipo = r["tipo"]

        if tipo == "alergia":
            chaves = _chaves_descricao(desc, tipo)
            chaves += sorted(chaves_classes.get(r["pa_id"], ()))
            chaves += sorted(chaves_sinonimos.get(r["pa_id"], ()))
            prefixo = r["pa"]
            cls = classes_por_pa.get(r["pa_id"])
            if cls:
                prefixo = f"{r['pa']} ({', '.join(cls)})"
            if _texto_casa(texto_alergias, chaves):
                alertas.append({
                    "tipo": "contraindicacao",
                    "severidade": r["severidade"],
                    "mensagem": f"{prefixo}: alergia registrada na anamnese ({desc}).",
                    "pa": r["pa"],
                })
            elif chaves_cruzadas.get(r["pa_id"]):
                if _texto_casa(texto_alergias, sorted(chaves_cruzadas[r["pa_id"]])):
                    ordem = {"grave": 0, "moderada": 1, "leve": 2}
                    sev, desc_cruz = min(
                        info_cruzadas.get(r["pa_id"], [("moderada", "")]),
                        key=lambda x: ordem.get(x[0], 9),
                    )
                    alertas.append({
                        "tipo": "contraindicacao",
                        "severidade": sev,
                        "mensagem": f"{prefixo}: reação cruzada — alergia registrada na anamnese ({desc_cruz or desc}).",
                        "pa": r["pa"],
                    })
        elif tipo == "gestacao":
            if gestante:
                alertas.append({
                    "tipo": "contraindicacao",
                    "severidade": r["severidade"],
                    "mensagem": f"{r['pa']}: contra-indicado na gravidez ({desc}).",
                    "pa": r["pa"],
                })
        elif tipo == "condicao":
            chaves = _chaves_descricao(desc, tipo)
            chaves += _variacoes_condicao(chaves)
            if _texto_casa(texto_condicoes, chaves):
                alertas.append({
                    "tipo": "contraindicacao",
                    "severidade": r["severidade"],
                    "mensagem": f"{r['pa']}: condição clínica compatível registrada ({desc}).",
                    "pa": r["pa"],
                })

    return alertas


def checar_medicamento_paciente(paciente_id, medicamento_id=None, nome_medicamento=None):
    pa_ids = resolver_principios_medicamento(medicamento_id, nome_medicamento)
    alertas = []
    alertas += checar_interacoes(paciente_id, pa_ids)
    alertas += checar_contra_indicacoes(paciente_id, pa_ids)
    return alertas


def alertas_paciente(paciente_id):
    ativos = medicamentos_ativos_paciente(paciente_id)
    alertas = []

    todos_pas = set()
    for med in ativos:
        pa_ids = resolver_principios_medicamento(med["medicamento_id"], med["nome_medicamento"])
        todos_pas |= expandir_sinonimos(pa_ids)

    ids = list(todos_pas)
    if ids:
        pn = ",".join(["%s"] * len(ids))
        rows = db.fetch_all(
            f"""SELECT a.nome AS pa_a, b.nome AS pa_b, i.severidade, i.descricao, i.conduta
                FROM interacoes_medicamentosas i
                JOIN principios_ativos a ON a.id = i.medicamento_a_id
                JOIN principios_ativos b ON b.id = i.medicamento_b_id
                WHERE i.medicamento_a_id IN ({pn}) AND i.medicamento_b_id IN ({pn})
                ORDER BY CASE i.severidade WHEN 'grave' THEN 1 WHEN 'moderada' THEN 2 ELSE 3 END""",
            ids + ids,
        )
        for r in rows:
            alertas.append({
                "tipo": "interacao",
                "severidade": r["severidade"],
                "mensagem": f"{r['pa_a']} + {r['pa_b']}: {r['descricao']}",
                "conduta": r["conduta"],
            })
        alertas += checar_contra_indicacoes(paciente_id, todos_pas)

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


def listar_sintomas():
    return db.fetch_all("SELECT id, nome FROM sintomas ORDER BY nome")


def sugestoes_por_sintoma_ids(sintoma_ids):
    if not sintoma_ids:
        return []
    ids = list(dict.fromkeys(sintoma_ids))
    ph = ",".join(["%s"] * len(ids))
    return db.fetch_all(
        f"""SELECT i.sintoma_id, s.nome AS sintoma, p.id AS principio_ativo_id, p.nome AS pa,
                   p.posologia, i.linha_tratamento, i.eficacia, i.observacoes
            FROM indicacoes i
            JOIN principios_ativos p ON p.id = i.principio_ativo_id
            JOIN sintomas s ON s.id = i.sintoma_id
            WHERE i.sintoma_id IN ({ph})
            ORDER BY i.sintoma_id, i.linha_tratamento, i.eficacia DESC""",
        ids,
    )


def sugestoes_seguras(paciente_id, sintoma_ids):
    sugestoes = sugestoes_por_sintoma_ids(sintoma_ids)
    if not sugestoes:
        return []

    pa_ids = {s["principio_ativo_id"] for s in sugestoes}
    interacoes = checar_interacoes(paciente_id, pa_ids)
    contra = checar_contra_indicacoes(paciente_id, pa_ids)

    alertas_por_pa = {}
    for a in interacoes:
        alertas_por_pa.setdefault(a["pa"], []).append(a)
        alertas_por_pa.setdefault(a["pa_b"], []).append(a)
    for a in contra:
        alertas_por_pa.setdefault(a["pa"], []).append(a)

    resultado = []
    for s in sugestoes:
        item = dict(s)
        item["alertas"] = alertas_por_pa.get(s["pa"], [])
        item["n_graves"] = sum(1 for a in item["alertas"] if a["severidade"] == "grave")
        item["n_moderadas"] = sum(1 for a in item["alertas"] if a["severidade"] == "moderada")
        resultado.append(item)
    return resultado
