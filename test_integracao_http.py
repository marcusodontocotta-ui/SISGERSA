"""Teste de integração HTTP (uvicorn real) do motor farmacológico.

Sobe um servidor uvicorn local automaticamente, executa os cenários por HTTP
(verificar medicamento, sugestões, painel de alertas, bloqueio por alerta grave
no fluxo de adicionar medicamento) e encerra o servidor ao final.

Requer banco Postgres com classes/sinônimos populados e um login válido de
profissional com permissão de editar prontuários.

Uso: python test_integracao_http.py
"""
import os
import re
import signal
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Credenciais do banco vem do .env (DATABASE_URL) ou das variaveis de ambiente.
os.environ.setdefault("DB_ENGINE", "postgresql")

from config import settings  # noqa: E402

if not settings.DATABASE_URL and not settings.DB_PASSWORD:
    raise SystemExit(
        "Credenciais do banco nao configuradas. Defina DATABASE_URL "
        "(ou DB_HOST/DB_USER/DB_PASSWORD/DB_NAME) no .env ou no ambiente."
    )

import requests  # noqa: E402

from database.connection import db  # noqa: E402

EMAILS = [f"tmp_integracao{i}@email.com" for i in range(1, 7)]


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def subir_servidor():
    porta = porta_livre()
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(porta)],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{porta}"
    ultimo = ""
    for _ in range(240):
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn encerrou antes de ficar pronto (code={proc.returncode})")
        try:
            r = requests.get(base + "/login", timeout=3)
            if r.status_code < 500:
                return proc, base
            ultimo = f"status={r.status_code}"
        except requests.RequestException as e:
            ultimo = str(e)
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError(f"uvicorn não respondeu a tempo (último: {ultimo})")


def derrubar_servidor(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


BASE = "http://127.0.0.1:8000"
LOGIN_EMAIL = "marcusodontocotta@gmail.com"
LOGIN_SENHA = "admin123"
results = []


def check(nome, cond, detalhe=""):
    results.append((nome, bool(cond)))
    print(("PASS" if cond else "FAIL"), nome, ("| " + str(detalhe) if detalhe else ""))


def pa_id(nome):
    return db.fetch_one("SELECT id FROM principios_ativos WHERE LOWER(nome)=LOWER(%s) LIMIT 1", (nome,))["id"]


def med_id(nome):
    return db.fetch_one("SELECT id FROM medicamentos WHERE LOWER(nome)=LOWER(%s) LIMIT 1", (nome,))


def limpar():
    for email in EMAILS:
        r = db.fetch_one("SELECT id FROM pacientes WHERE email=%s", (email,))
        if r:
            db.execute("DELETE FROM prontuarios WHERE paciente_usuario_id=%s", (r["id"],))
            db.execute("DELETE FROM paciente_medicamentos WHERE paciente_id=%s", (r["id"],))
            db.execute("DELETE FROM anamnese WHERE paciente_id=%s", (r["id"],))
            db.execute("DELETE FROM pacientes WHERE id=%s", (r["id"],))


def novo_paciente(email, alergias, historico=""):
    db.execute("INSERT INTO pacientes (nome, email, senha_hash) VALUES (%s,%s,%s)", ("Tmp Integracao", email, "x"))
    pid = db.fetch_one("SELECT id FROM pacientes WHERE email=%s", (email,))["id"]
    db.execute("INSERT INTO anamnese (paciente_id, alergias, gestante, historico_medico) VALUES (%s,%s,FALSE,%s)",
               (pid, alergias, historico))
    return pid


def adicionar_med(paciente_id, nome):
    m = med_id(nome)
    if m:
        db.execute("INSERT INTO paciente_medicamentos (paciente_id, medicamento_id, nome_medicamento, ativo) VALUES (%s,%s,NULL,TRUE)",
                   (paciente_id, m["id"]))


def main():
    limpar()
    pid = novo_paciente(EMAILS[0], "alergia a cefalosporinas e penicilina", "historico de ulcera gastrica")
    pid2 = novo_paciente(EMAILS[1], "alergia a zitromax")
    pid3 = novo_paciente(EMAILS[2], "alergia a tylenol")
    pid4 = novo_paciente(EMAILS[3], "", "")          # so metronidazol ativo -> verificar varfarina (interacao)
    adicionar_med(pid4, "FLAGYL")
    pid5 = novo_paciente(EMAILS[4], "", "")          # metronidazol + varfarina ativos -> painel Interação
    adicionar_med(pid5, "FLAGYL")
    adicionar_med(pid5, "VARFARINA")
    pid6 = novo_paciente(EMAILS[5], "alergia a cefalosporinas")  # bloqueio por alerta grave

    m = med_id("cefalexina")
    if m:
        db.execute("INSERT INTO paciente_medicamentos (paciente_id, medicamento_id, nome_medicamento, ativo) VALUES (%s,%s,NULL,TRUE)",
                   (pid, m["id"]))

    amox = med_id("amoxicilina")

    try:
        S = requests.Session()
        r = S.post(BASE + "/login", data={"email": LOGIN_EMAIL, "senha": LOGIN_SENHA}, allow_redirects=False)
        check("login profissional", r.status_code in (200, 303, 302), f"status={r.status_code}")

        # --- verificar por nome de sinonimo (keflex -> cefalexina, alergia cefalosporinas) ---
        r = S.post(BASE + f"/pacientes/{pid}/medicamentos/verificar",
                   data={"nome_medicamento": "keflex", "embedded": ""})
        check("HTTP verificar 'keflex' responde", r.status_code == 200, f"status={r.status_code}")
        d = r.json()
        msgs = [a.get("mensagem") for a in d.get("alertas", [])]
        check("HTTP verificar 'keflex' gera alerta de alergia", any("alergia" in m.lower() for m in msgs), str(msgs))
        check("HTTP alerta com classe no prefixo", any("Cefalosporinas" in m for m in msgs), str(msgs))

        # --- verificar por medicamento (amoxicilina, alergia penicilina) ---
        if amox:
            r = S.post(BASE + f"/pacientes/{pid}/medicamentos/verificar",
                       data={"medicamento_id": amox["id"], "embedded": ""})
            d = r.json()
            msgs = [a.get("mensagem") for a in d.get("alertas", [])]
            check("HTTP verificar amoxicilina gera alerta direto penicilina",
                  any("penicilina" in m.lower() for m in msgs), str(msgs))

        # --- verificar por sinonimo popular: zitromax -> azitromicina (alergia a zitromax) ---
        azi = med_id("AZI")
        if azi:
            r = S.post(BASE + f"/pacientes/{pid2}/medicamentos/verificar",
                       data={"medicamento_id": azi["id"], "embedded": ""})
            d = r.json()
            msgs = [a.get("mensagem") for a in d.get("alertas", [])]
            check("HTTP sinonimo 'zitromax' alerta p/ azitromicina (Macrolideos)",
                  any("alergia" in m.lower() and "Macrolídeos" in m for m in msgs), str(msgs))

        # --- verificar por sinonimo popular: tylenol -> paracetamol (alergia a tylenol) ---
        agud = med_id("AGUD")
        if agud:
            r = S.post(BASE + f"/pacientes/{pid3}/medicamentos/verificar",
                       data={"medicamento_id": agud["id"], "embedded": ""})
            d = r.json()
            msgs = [a.get("mensagem") for a in d.get("alertas", [])]
            check("HTTP sinonimo 'tylenol' alerta p/ paracetamol",
                  any("alergia" in m.lower() and "paracetamol" in m.lower() for m in msgs), str(msgs))

        # --- interacao metronidazol + varfarina (tipo interacao no JSON, usado p/ badge JS) ---
        varf = med_id("VARFARINA")
        if varf:
            r = S.post(BASE + f"/pacientes/{pid4}/medicamentos/verificar",
                       data={"medicamento_id": varf["id"], "embedded": ""})
            d = r.json()
            ints = [a for a in d.get("alertas", []) if a.get("tipo") == "interacao"]
            check("HTTP verificar varfarina gera alerta tipo 'interacao'",
                  any("varfarina" in (a.get("mensagem") or "").lower() for a in ints),
                  str([(a.get("tipo"), a.get("mensagem")) for a in d.get("alertas", [])]))

        # --- sugestoes (sintoma 47 = dor de dente aguda) ---
        r = S.post(BASE + f"/pacientes/{pid}/sugestoes", data=[("sintoma_ids", "47")])
        check("HTTP sugestoes responde", r.status_code == 200, f"status={r.status_code}")
        d = r.json()
        sug = d.get("sugestoes", [])
        check("HTTP sugestoes retorna itens", len(sug) > 0, f"qtd={d.get('quantidade')}")
        if sug:
            aines = [s for s in sug if s.get("pa", "").lower() in
                     ("ibuprofeno", "diclofenaco de sódio", "naproxeno", "nimesulida")]
            check("HTTP sugestoes marca graves p/ AINE (ulcera)", aines and all(s.get("n_graves", 0) > 0 for s in aines),
                  str([(s["pa"], s["n_graves"]) for s in aines]))

        # --- pagina anamnese: painel de alertas ---
        r = S.get(BASE + f"/pacientes/{pid}/anamnese?tab=medicamentos")
        check("HTTP pagina anamnese responde", r.status_code == 200, f"status={r.status_code}")
        check("HTTP painel alertas_farmaco renderiza", bool(re.search(r"Alertas farmacológicos", r.text)))
        check("HTTP painel inclui classe na mensagem", "Cefalosporinas" in r.text)
        check("HTTP painel mostra badge Contra-indicação", "Contra-indicação" in r.text)

        # --- pagina anamnese do paciente5: interacao entre ativos -> badge Interação ---
        r = S.get(BASE + f"/pacientes/{pid5}/anamnese?tab=medicamentos")
        check("HTTP painel interacao mostra badge Interação", r.status_code == 200 and "Interação" in r.text)

        # --- bloqueio por alerta grave ao adicionar medicamento ---
        from urllib.parse import unquote
        if m:
            antes = db.fetch_one("SELECT COUNT(*) AS n FROM paciente_medicamentos WHERE paciente_id=%s", (pid6,))["n"]
            r = S.post(BASE + f"/pacientes/{pid6}/medicamentos",
                       data={"medicamento_id": m["id"], "nome_medicamento": "", "dose": "500mg", "frequencia": "8/8h", "via": "VO", "embedded": "1"},
                       allow_redirects=False)
            depois = db.fetch_one("SELECT COUNT(*) AS n FROM paciente_medicamentos WHERE paciente_id=%s", (pid6,))["n"]
            loc = unquote(r.headers.get("Location", ""))
            bloqueou = r.status_code == 302 and "erro=" in loc and "Medicamento não adicionado" in loc
            check("HTTP adicionar med bloqueia alerta grave", bloqueou and depois == antes,
                  f"status={r.status_code} loc={loc} antes={antes} depois={depois}")

            r = S.post(BASE + f"/pacientes/{pid6}/medicamentos",
                       data={"medicamento_id": m["id"], "nome_medicamento": "", "dose": "500mg", "frequencia": "8/8h", "via": "VO", "embedded": "1", "confirmar_grave": "1"},
                       allow_redirects=False)
            depois = db.fetch_one("SELECT COUNT(*) AS n FROM paciente_medicamentos WHERE paciente_id=%s", (pid6,))["n"]
            permitiu = r.status_code == 302 and "erro=" not in r.headers.get("Location", "")
            check("HTTP adicionar med com confirmacao de grave insere", permitiu and depois == antes + 1,
                  f"status={r.status_code} loc={r.headers.get('Location', '')} depois={depois}")

            # --- painel de alertas no prontuário do paciente6 (cefalexina ativa + alergia) ---
            db.execute("INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s,%s,%s)",
                       (pid6, 4, f"PRONT-TMP-{pid6}"))
            pront_id = db.fetch_one(
                "SELECT id FROM prontuarios WHERE paciente_usuario_id=%s AND estabelecimento_id=%s ORDER BY id DESC LIMIT 1",
                (pid6, 4))["id"]
            r = S.get(BASE + f"/prontuarios/{pront_id}")
            check("HTTP prontuario mostra painel alertas farmacologicos",
                  r.status_code == 200 and "Alertas farmacológicos" in r.text,
                  f"status={r.status_code}")
            check("HTTP prontuario painel inclui alergia cefalexina",
                  r.status_code == 200 and "cefalexina" in r.text.lower() and "Cefalosporinas" in r.text,
                  f"status={r.status_code}")
    finally:
        limpar()


if __name__ == "__main__":
    proc, base = subir_servidor()
    try:
        BASE = base
        main()
    finally:
        derrubar_servidor(proc)

    fails = [x for x in results if not x[1]]
    print(f"\n=== {len(results) - len(fails)}/{len(results)} PASS ===")
    sys.exit(1 if fails else 0)
