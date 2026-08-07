"""Teste de regressão do motor farmacológico (utils/farmaco.py).

Cobre: matching de alergias por classe farmacológica, sinônimos populares,
reação cruzada penicilina-cefalosporina, fronteira de palavra (sem falsos
positivos de substring), sinônimos de condição clínica e resolução de
medicamento por nome/sinônimo.

Requer banco Postgres com as tabelas de classe/sinônimos populadas
(rodar seed_classes_farmacologicas.py e seed_sinonimos_populares.py antes).

Uso: python test_farmaco.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Credenciais do banco vem do .env (DATABASE_URL) ou das variaveis de ambiente.
os.environ.setdefault("DB_ENGINE", "postgresql")

from config import settings  # noqa: E402

if not settings.DATABASE_URL and not settings.DB_PASSWORD:
    raise SystemExit(
        "Credenciais do banco nao configuradas. Defina DATABASE_URL "
        "(ou DB_HOST/DB_USER/DB_PASSWORD/DB_NAME) no .env ou no ambiente."
    )

from database.connection import db  # noqa: E402
from utils.farmaco import (  # noqa: E402
    _chaves_descricao,
    _texto_casa,
    _variacoes_condicao,
    _variantes_plural,
    checar_contra_indicacoes,
    checar_medicamento_paciente,
    expandir_sinonimos,
    resolver_principios_medicamento,
)

EMAIL_TMP = "tmp_regressao@email.com"

_RESULTS = []


def check(nome, cond, detalhe=""):
    _RESULTS.append((nome, bool(cond)))
    print(f"[{'OK ' if cond else 'FAIL'}] {nome}" + (f"  | {detalhe}" if detalhe else ""))


def _limpar_tmp():
    r = db.fetch_one("SELECT id FROM pacientes WHERE email = %s", (EMAIL_TMP,))
    if r:
        db.execute("DELETE FROM anamnese WHERE paciente_id = %s", (r["id"],))
        db.execute("DELETE FROM pacientes WHERE id = %s", (r["id"],))


def _novo_paciente(alergias="", historico=""):
    _limpar_tmp()
    db.execute("INSERT INTO pacientes (nome, email, senha_hash) VALUES (%s,%s,%s)",
               ("Teste Regressao", EMAIL_TMP, "x"))
    pid = db.fetch_one("SELECT id FROM pacientes WHERE email = %s", (EMAIL_TMP,))["id"]
    db.execute(
        "INSERT INTO anamnese (paciente_id, alergias, gestante, historico_medico) VALUES (%s, %s, FALSE, %s)",
        (pid, alergias, historico),
    )
    return pid


def _pa(nome):
    r = db.fetch_one("SELECT id FROM principios_ativos WHERE LOWER(nome) = LOWER(%s) LIMIT 1", (nome,))
    if not r:
        raise AssertionError(f"PA não encontrado: {nome}")
    return r["id"]


def _tem_alergia(alertas):
    return any(a["tipo"] == "contraindicacao" and "alergia" in a["mensagem"] for a in alertas)


def _tem_condicao(alertas):
    return any(a["tipo"] == "contraindicacao" and "condi" in a["mensagem"].lower() for a in alertas)


def test_texto_casa():
    check("texto: 'sulfa' em 'sulfato ferroso' é falso positivo e deve ser False",
          _texto_casa("sulfato ferroso", ["sulfa"]) is False)
    check("texto: 'sulfa' isolado casa", _texto_casa("sulfa", ["sulfa"]) is True)
    check("texto: chave no meio com fronteira", _texto_casa("alergia a cefalosporinas", ["cefalosporina"]) is True)
    check("texto: chave composta contida", _texto_casa("uso de aspirina diario", ["aspirina"]) is True)
    check("texto: variante plural", _texto_casa("cefalosporinas", ["cefalosporina"]) is True)
    check("texto: variantes_plural de 'cefalosporina'", "cefalosporinas" in _variantes_plural("cefalosporina"))
    check("texto: chaves_descricao alergia remove prefixo",
          _chaves_descricao("Alergia a cefalosporinas", "alergia") == ["cefalosporinas"])


def test_alergia_classe():
    casos = [
        ("classe exato", "cefalexina", "cefalexina", True),
        ("classe singular", "cefalosporina", "cefalexina", True),
        ("classe plural", "cefalosporinas", "cefalexina", True),
        ("classe + prefixo", "alergia a cefalosporinas", "cefalexina", True),
        ("penicilinas -> amoxicilina", "penicilinas", "amoxicilina", True),
        ("membro -> membro", "amoxicilina", "clavulanato de potássio", True),
        ("AINE membro -> membro", "ibuprofeno", "diclofenaco de sódio", True),
        ("sinonimo popular de membro", "aspirina", "ibuprofeno", True),
        ("sem alergia -> sem alerta", "", "cefalexina", False),
        ("sem falso positivo sulfa", "sulfato ferroso", "amoxicilina", False),
        ("sem falso positivo cafeina", "cafeina", "ibuprofeno", False),
    ]
    for nome, alergia, pa_nome, esperado in casos:
        pid = _novo_paciente(alergia)
        alertas = checar_contra_indicacoes(pid, {_pa(pa_nome)})
        check(f"alergia/classe: {nome}", _tem_alergia(alertas) == esperado,
              f"'{alergia}' x {pa_nome} -> {_tem_alergia(alertas)}")
        _limpar_tmp()


def test_alergia_sinonimos_populares():
    casos = [
        ("keflex -> cefalexina", "keflex", "cefalexina", True),
        ("amoxil -> amoxicilina", "amoxil", "amoxicilina", True),
        ("amoxil -> clavulanato", "amoxil", "clavulanato de potássio", True),
        ("novalgina -> dipirona", "novalgina", "dipirona", True),
        ("voltaren -> ibuprofeno", "voltaren", "ibuprofeno", True),
        ("flagyl -> metronidazol", "flagyl", "metronidazol", True),
        ("dalsy -> ibuprofeno", "dalsy", "ibuprofeno", True),
        ("ibupirac -> ibuprofeno", "ibupirac", "ibuprofeno", True),
        ("tylenol -> paracetamol", "tylenol", "paracetamol", True),
        ("zitromax -> azitromicina", "zitromax", "azitromicina", True),
        ("vibramicina -> doxiciclina", "vibramicina", "doxiciclina", True),
        ("meticorten -> prednisona", "meticorten", "prednisona", True),
        ("dalacin -> clindamicina", "dalacin", "clindamicina", True),
        ("nexium -> esomeprazol", "nexium", "esomeprazol magnésico", True),
        ("cataflam -> diclofenaco potássico", "cataflam", "diclofenaco potássico", True),
        ("anador -> dipirona", "anador", "dipirona", True),
        ("tachipirina -> paracetamol", "tachipirina", "paracetamol", True),
        ("buscofem -> ibuprofeno", "buscofem", "ibuprofeno", True),
        ("nisulid -> nimesulida", "nisulid", "nimesulida", True),
        ("ponstan -> ácido mefenâmico", "ponstan", "ácido mefenâmico", True),
        ("profenid -> cetoprofeno", "profenid", "cetoprofeno", True),
        ("decadron -> dexametasona", "decadron", "dexametasona", True),
        ("zovirax -> aciclovir", "zovirax", "aciclovir", True),
        ("losec -> omeprazol", "losec", "omeprazol", True),
        ("xylocaina -> lidocaína", "xylocaina", "lidocaína", True),
        ("clavamox -> amoxicilina", "clavamox", "amoxicilina", True),
        ("bactrim -> sulfametoxazol", "bactrim", "sulfametoxazol", True),
    ]
    for nome, alergia, pa_nome, esperado in casos:
        pid = _novo_paciente(alergia)
        alertas = checar_contra_indicacoes(pid, {_pa(pa_nome)})
        check(f"alergia/sinonimo: {nome}", _tem_alergia(alertas) == esperado,
              f"'{alergia}' x {pa_nome} -> {_tem_alergia(alertas)}")
        _limpar_tmp()


def test_sinonimos_afins():
    casos = [
        ("lidocaína -> cloridrato de lidocaina", "lidocaína", "cloridrato de lidocaina", True),
        ("lidocaína monoidratada -> cloridrato de lidocaina", "cloridrato de lidocaína monoidratada", "cloridrato de lidocaina", True),
        ("anestésicos locais -> articaína", "anestésicos locais", "cloridrato de articaína", True),
        ("anestésicos locais -> mepivacaína", "anestésicos locais", "cloridrato de mepivacaína", True),
        ("anestésicos locais -> prilocaína", "anestésicos locais", "prilocaína", True),
        ("anestésicos locais -> cloridrato de prilocaína", "anestésicos locais", "cloridrato de prilocaína", True),
        ("ácido acetil salicilico -> ácido acetilsalicílico", "ácido acetil salicilico", "ácido acetilsalicílico", True),
    ]
    for nome, alergia, pa_nome, esperado in casos:
        pid = _novo_paciente(alergia)
        alertas = checar_contra_indicacoes(pid, {_pa(pa_nome)})
        check(f"afins: {nome}", _tem_alergia(alertas) == esperado,
              f"'{alergia}' x {pa_nome} -> {_tem_alergia(alertas)}")
        _limpar_tmp()

    # resolução de sinonimos afins (independe de registro de alergia)
    pa = expandir_sinonimos({_pa("oxido de zinco")})
    check("afins: 'oxido de zinco' resolve para 'óxido de zinco'", _pa("óxido de zinco") in pa, str(pa))
    pa = expandir_sinonimos({_pa("cloridrato de prilocaína")})
    check("afins: 'cloridrato de prilocaína' resolve para 'prilocaína'", _pa("prilocaína") in pa, str(pa))


def test_reacao_cruzada():
    casos = [
        ("cefalexina + alergia penicilina", "alergia a penicilina", "cefalexina", True, "cruzada"),
        ("amoxicilina + alergia cefalosporina", "alergia a cefalosporinas", "amoxicilina", True, "cruzada"),
        ("classe distinta sem cruzada (macrolideo)", "alergia a penicilina", "azitromicina", False, None),
        ("alerta direto nao fala cruzada", "alergia a cefalosporinas", "cefalexina", True, "direto"),
    ]
    for nome, alergia, pa_nome, esperado, modo in casos:
        pid = _novo_paciente(alergia)
        alertas = checar_contra_indicacoes(pid, {_pa(pa_nome)})
        if not esperado:
            check(f"cruzada: {nome}", not _tem_alergia(alertas))
        elif modo == "cruzada":
            check(f"cruzada: {nome}",
                  _tem_alergia(alertas) and any("cruzada" in a["mensagem"] for a in alertas),
                  str([a["mensagem"] for a in alertas]))
        else:
            check(f"cruzada: {nome}",
                  _tem_alergia(alertas) and all("cruzada" not in a["mensagem"] for a in alertas),
                  str([a["mensagem"] for a in alertas]))
        _limpar_tmp()


def test_mensagem_classe():
    pid = _novo_paciente("alergia a cefalosporinas")
    alertas = checar_contra_indicacoes(pid, {_pa("cefalexina")})
    check("mensagem/classe: inclui classe no prefixo",
          any("cefalexina (Cefalosporinas):" in a["mensagem"] for a in alertas),
          str([a["mensagem"] for a in alertas]))
    _limpar_tmp()


def test_condicao():
    casos = [
        ("gastrite -> ulcera peptica", "paciente com gastrite cronica", "naproxeno", True),
        ("ulcera -> ulcera peptica", "historico de ulcera", "ibuprofeno", True),
        ("insuficiencia renal -> renal grave", "insuficiencia renal cronica", "ibuprofeno", True),
        ("doenca renal -> renal grave", "doenca renal terminal", "diclofenaco de sódio", True),
        ("cirrose -> insuf hepatica", "cirrose hepatica", "paracetamol", True),
        ("diabetes -> diabetes descompensado", "diabetes mellitus tipo 2", "dexametasona", True),
        ("icc -> doenca cardiaca", "insuficiencia cardiaca (icc)", "diclofenaco de sódio", True),
        ("sepse -> infeccao sistemica", "sepse grave", "prednisona", True),
        ("etilismo -> alcool", "etilismo cronico", "metronidazol", True),
        ("criancas -> mancha dentaria", "criancas menores de 8 anos", "doxiciclina", True),
        ("prolongamento qt -> interacao qt", "prolongamento do intervalo qt", "cetoconazol", True),
        ("texto exato da condicao", "úlcera péptica ativa", "naproxeno", True),
        ("hemofilia -> discrasias", "paciente hemofilico", "dipirona", True),
        ("coagulopatia -> discrasias", "coagulopatia adquirida", "dipirona", True),
        ("nefropatia diabetica -> renal grave", "nefropatia diabetica", "ibuprofeno", True),
        ("sem condicao -> sem alerta", "", "naproxeno", False),
    ]
    for nome, historico, pa_nome, esperado in casos:
        pid = _novo_paciente("", historico)
        alertas = checar_contra_indicacoes(pid, {_pa(pa_nome)})
        check(f"condicao: {nome}", _tem_condicao(alertas) == esperado,
              f"'{historico}' x {pa_nome} -> {_tem_condicao(alertas)}")
        _limpar_tmp()
    v = _variacoes_condicao(_chaves_descricao("Úlcera péptica ativa", "condicao"))
    check("condicao: variacoes de ulcera incluem 'gastrite'", "gastrite" in v, str(v))


def test_resolucao():
    def canonico_de(sinonimo):
        r = db.fetch_one(
            """SELECT ps.canonico_id FROM principio_sinonimos ps
               JOIN principios_ativos s ON s.id = ps.sinonimo_id
               WHERE LOWER(s.nome) = LOWER(%s) LIMIT 1""", (sinonimo,))
        return r["canonico_id"] if r else None

    pa = resolver_principios_medicamento(nome_medicamento="keflex")
    check("resolucao: 'keflex' resolve para canonico cefalexina",
          canonico_de("keflex") in expandir_sinonimos(pa), str(pa))
    pa = resolver_principios_medicamento(nome_medicamento="tylenol")
    check("resolucao: 'tylenol' resolve para paracetamol", _pa("paracetamol") in expandir_sinonimos(pa), str(pa))
    pa = resolver_principios_medicamento(nome_medicamento="xyznaoexiste999")
    check("resolucao: nome inexistente retorna vazio", pa == set())

    pid = _novo_paciente("alergia a cefalosporinas")
    alertas = checar_medicamento_paciente(pid, nome_medicamento="keflex")
    check("resolucao: fluxo completo 'keflex' dispara alerta",
          any("alergia" in a["mensagem"] for a in alertas), str([a["mensagem"] for a in alertas]))
    _limpar_tmp()


def main():
    _limpar_tmp()
    try:
        test_texto_casa()
        test_alergia_classe()
        test_alergia_sinonimos_populares()
        test_sinonimos_afins()
        test_reacao_cruzada()
        test_mensagem_classe()
        test_condicao()
        test_resolucao()
    finally:
        _limpar_tmp()

    n_ok = sum(1 for _, ok in _RESULTS if ok)
    n_fail = len(_RESULTS) - n_ok
    print(f"\n=== {n_ok}/{len(_RESULTS)} PASS, {n_fail} FAIL ===")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
