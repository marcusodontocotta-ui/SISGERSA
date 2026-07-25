"""
SISGERSA - Auditoria Completa de Todas as 80 Rotas
Testa GET/POST, autenticacao, permissoes, e fluxo completo.
"""
import sys
sys.path.insert(0, ".")

from main import app
from starlette.testclient import TestClient
from database.connection import db

db.get_connection()

PASSADOS = 0
FALHADOS = 0
ERROS = []

def ok(route, msg=""):
    global PASSADOS
    PASSADOS += 1
    print(f"  [OK] {route} {msg}")

def fail(route, msg):
    global FALHADOS
    FALHADOS += 1
    ERROS.append((route, msg))
    print(f"  [FALHOU] {route} -> {msg}")

def setup_data():
    db.execute("SET FOREIGN_KEY_CHECKS = 0")
    db.execute("DELETE FROM tratamentos")
    db.execute("DELETE FROM evolucoes")
    db.execute("DELETE FROM imaging")
    db.execute("DELETE FROM consultas")
    db.execute("DELETE FROM prontuarios")
    db.execute("DELETE FROM orcamento_itens")
    db.execute("DELETE FROM orcamentos")
    db.execute("DELETE FROM pagamentos")
    db.execute("DELETE FROM paciente_convenio")
    db.execute("DELETE FROM paciente_estabelecimento")
    db.execute("DELETE FROM profissional_estabelecimento")
    db.execute("DELETE FROM permissoes_usuario")
    db.execute("DELETE FROM permissoes_paciente")
    db.execute("DELETE FROM log_atividades")
    db.execute("DELETE FROM estoque")
    db.execute("DELETE FROM procedimento_valor")
    db.execute("DELETE FROM convenios")
    db.execute("DELETE FROM procedimentos")
    db.execute("DELETE FROM usuarios WHERE id > 1")
    db.execute("DELETE FROM estabelecimentos")
    db.execute("SET FOREIGN_KEY_CHECKS = 1")

    c = db.execute(
        "INSERT INTO estabelecimentos (nome, tipo) VALUES (%s, %s)",
        ("Clinica Teste Audit", "clinica"),
    )
    estab_id = c.lastrowid
    db.execute(
        "UPDATE usuarios SET is_super = TRUE WHERE id = 1"
    )

    c = db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo, is_super) VALUES (%s, %s, %s, %s, %s)",
        ("Admin Local", "admin_audit@test.com", "$2b$12$LJ3m4ys3GzJx2VE0y9q8YOfK2JGqz1kH5y6QJ5bG5rG5hG5rG5hG", "admin", False),
    )
    admin_id = c.lastrowid
    c = db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s)",
        ("Recepcionista", "recepcionista_audit@test.com", "$2b$12$LJ3m4ys3GzJx2VE0y9q8YOfK2JGqz1kH5y6QJ5bG5rG5hG5rG5hG", "recepcionista"),
    )
    recep_id = c.lastrowid
    c = db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s)",
        ("Profissional", "prof_audit@test.com", "$2b$12$LJ3m4ys3GzJx2VE0y9q8YOfK2JGqz1kH5y6QJ5bG5rG5hG5rG5hG", "profissional"),
    )
    prof_id = c.lastrowid
    c = db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s)",
        ("Paciente", "paciente_audit@test.com", "$2b$12$LJ3m4ys3GzJx2VE0y9q8YOfK2JGqz1kH5y6QJ5bG5rG5hG5rG5hG", "paciente"),
    )
    pac_id = c.lastrowid

    db.execute("INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s)", (prof_id, estab_id))
    db.execute("INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s)", (admin_id, estab_id))
    db.execute("INSERT INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s)", (pac_id, estab_id))

    return {
        "estab_id": estab_id,
        "admin_id": admin_id,
        "recep_id": recep_id,
        "prof_id": prof_id,
        "pac_id": pac_id,
    }


def login(client, email, senha):
    r = client.post("/login", data={"email": email, "senha": senha})
    return r


def get_cookie_estab(client, estab_id):
    client.cookies.set("estabelecimento_id", str(estab_id))


def test_rotas():
    global PASSADOS, FALHADOS, ERROS

    print("=" * 70)
    print("AUDITORIA COMPLETA - SISGERSA (80 Rotas)")
    print("=" * 70)

    c = TestClient(app, raise_server_exceptions=False)

    # ─── SETUP ──────────────────────────────────────────────
    print("\n--- SETUP: Dados de teste ---")
    dados = setup_data()
    estab_id = dados["estab_id"]
    admin_id = dados["admin_id"]
    recep_id = dados["recep_id"]
    prof_id = dados["prof_id"]
    pac_id = dados["pac_id"]
    print(f"  estab_id={estab_id} admin={admin_id} recep={recep_id} prof={prof_id} pac={pac_id}")

    # ─── AUTH: Login admin super ────────────────────────────
    print("\n--- 1. AUTENTICACAO ---")
    r = login(c, "marcusodontocotta@gmail.com", "admin123")
    if r.status_code in (302, 200):
        ok("POST /login (super admin)", f"status={r.status_code}")
    else:
        fail("POST /login (super admin)", f"status={r.status_code}")

    r = c.get("/dashboard")
    if r.status_code == 200:
        ok("GET /dashboard", "200")
    else:
        fail("GET /dashboard", f"status={r.status_code}")

    # Seletor de estabelecimento
    r = c.post("/estabelecimento/selecionar", data={"estabelecimento_id": str(estab_id)}, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /estabelecimento/selecionar", f"redirect")
    else:
        fail("POST /estabelecimento/selecionar", f"status={r.status_code}")

    # ─── 2. ROTAS PUBLICAS ──────────────────────────────────
    print("\n--- 2. ROTAS PUBLICAS ---")

    c2 = TestClient(app, raise_server_exceptions=False)
    r = c2.get("/")
    if r.status_code in (200, 302):
        ok("GET /", f"status={r.status_code}")
    else:
        fail("GET /", f"status={r.status_code}")

    r = c2.get("/login")
    if r.status_code == 200:
        ok("GET /login", "200")
    else:
        fail("GET /login", f"status={r.status_code}")

    r = c2.get("/registrar")
    if r.status_code == 200:
        ok("GET /registrar", "200")
    else:
        fail("GET /registrar", f"status={r.status_code}")

    r = c2.get("/api/status")
    if r.status_code == 200:
        ok("GET /api/status", "200")
    else:
        fail("GET /api/status", f"status={r.status_code}")

    # Logout
    r = c.get("/logout", follow_redirects=False)
    if r.status_code in (302, 307):
        ok("GET /logout", f"redirect")
    else:
        fail("GET /logout", f"status={r.status_code}")

    r = c.get("/dashboard", follow_redirects=False)
    if r.status_code in (302, 307):
        ok("GET /dashboard (sem login)", f"redirect para login")
    else:
        fail("GET /dashboard (sem login)", f"status={r.status_code}")

    # ─── 3. RE-LOGIN E SETUP PERMICOES ──────────────────────
    print("\n--- 3. SETUP DE PERMISSOES ---")
    login(c, "marcusodontocotta@gmail.com", "admin123")
    c.cookies.set("estabelecimento_id", str(estab_id))

    from utils.auth import criar_usuario, vincular_paciente, vincular_profissional, hash_senha

    # Create a recepcionista linked to estab
    h = hash_senha("test123")
    db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE id=id",
        ("Recepcionista Audit", "recepcionista_audit@test.com", h, "recepcionista"),
    )
    u = db.fetch_one("SELECT id FROM usuarios WHERE email = 'recepcionista_audit@test.com'")
    recep_id = u["id"]
    db.execute(
        "INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE id=id",
        (recep_id, estab_id),
    )

    # Create a profissional linked to estab
    db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE id=id",
        ("Prof Audit", "prof_audit@test.com", h, "profissional"),
    )
    u = db.fetch_one("SELECT id FROM usuarios WHERE email = 'prof_audit@test.com'")
    prof_id = u["id"]
    db.execute(
        "INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE id=id",
        (prof_id, estab_id),
    )

    # Create a paciente linked to estab
    db.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, tipo) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE id=id",
        ("Paciente Audit", "paciente_audit@test.com", h, "paciente"),
    )
    u = db.fetch_one("SELECT id FROM usuarios WHERE email = 'paciente_audit@test.com'")
    pac_id = u["id"]
    db.execute(
        "INSERT INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE id=id",
        (pac_id, estab_id),
    )

    print(f"  Admin={admin_id}, Recep={recep_id}, Prof={prof_id}, Pac={pac_id}, Estab={estab_id}")

    # ─── 4. ADMIN: CUPONS ───────────────────────────────────
    print("\n--- 4. ADMIN: CUPONS ---")
    r = c.get("/admin/cupons")
    if r.status_code == 200:
        ok("GET /admin/cupons", "200")
    else:
        fail("GET /admin/cupons", f"status={r.status_code}")

    r = c.post("/admin/cupons/criar", data={
        "codigo": "TESTE_AUDIT",
        "descricao": "Cupom de teste",
        "desconto_percentual": "10",
        "plano_destino": "basico",
        "validade_dias": "30",
        "max_usos": "10",
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /admin/cupons/criar", f"redirect")
    else:
        fail("POST /admin/cupons/criar", f"status={r.status_code}")

    cupom = db.fetch_one("SELECT id FROM cupons WHERE codigo = 'TESTE_AUDIT'")
    if cupom:
        r = c.post(f"/admin/cupons/{cupom['id']}/toggle", follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /admin/cupons/{id}/toggle", f"redirect")
        else:
            fail("POST /admin/cupons/{id}/toggle", f"status={r.status_code}")
    else:
        fail("POST /admin/cupons/criar", "cupom nao foi criado no DB")

    # ─── 5. ADMIN: PERMISSOES ───────────────────────────────
    print("\n--- 5. ADMIN: PERMISSOES ---")
    r = c.get(f"/admin/permissoes?estabelecimento_id={estab_id}")
    if r.status_code == 200:
        ok("GET /admin/permissoes", "200")
    else:
        fail("GET /admin/permissoes", f"status={r.status_code}")

    r = c.post("/admin/permissoes/salvar", data={
        "usuario_id": str(recep_id),
        "estabelecimento_id": str(estab_id),
        "pacientes_ver": "on",
        "pacientes_criar": "on",
        "pacientes_editar": "on",
        "consultas_ver": "on",
        "consultas_criar": "on",
        "consultas_editar": "on",
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /admin/permissoes/salvar", "redirect")
    else:
        fail("POST /admin/permissoes/salvar", f"status={r.status_code}")

    # ─── 6. API: USUARIOS POR ESTAB ─────────────────────────
    print("\n--- 6. API: USUARIOS POR ESTAB ---")
    r = c.get(f"/api/usuarios-por-estab?estabelecimento_id={estab_id}")
    if r.status_code == 200:
        ok("GET /api/usuarios-por-estab", "200")
    else:
        fail("GET /api/usuarios-por-estab", f"status={r.status_code}")

    # ─── 7. API: DASHBOARD STATS ────────────────────────────
    print("\n--- 7. API: DASHBOARD STATS ---")
    r = c.get("/api/dashboard-stats?periodo=mes")
    if r.status_code == 200:
        ok("GET /api/dashboard-stats", "200")
    else:
        fail("GET /api/dashboard-stats", f"status={r.status_code}")

    # ─── 8. API: ESTABELECIMENTOS ───────────────────────────
    print("\n--- 8. API: ESTABELECIMENTOS ---")
    r = c.get("/api/estabelecimentos")
    if r.status_code == 200:
        ok("GET /api/estabelecimentos", "200")
    else:
        fail("GET /api/estabelecimentos", f"status={r.status_code}")

    # ─── 9. ESTABELECIMENTOS CRUD ───────────────────────────
    print("\n--- 9. ESTABELECIMENTOS CRUD ---")
    r = c.get("/estabelecimentos")
    if r.status_code == 200:
        ok("GET /estabelecimentos", "200")
    else:
        fail("GET /estabelecimentos", f"status={r.status_code}")

    r = c.post("/estabelecimentos/criar", data={
        "nome": "Estab Teste Audit",
        "tipo": "clinica",
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /estabelecimentos/criar", "redirect")
    else:
        fail("POST /estabelecimentos/criar", f"status={r.status_code}")

    novo_estab = db.fetch_one("SELECT id FROM estabelecimentos WHERE nome = 'Estab Teste Audit'")
    if novo_estab:
        eid = novo_estab["id"]
        r = c.get(f"/estabelecimentos/{eid}/editar")
        if r.status_code == 200:
            ok("GET /estabelecimentos/{id}/editar", "200")
        else:
            fail("GET /estabelecimentos/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/estabelecimentos/{eid}/editar", data={
            "nome": "Estab Teste Audit Editado",
            "tipo": "hospital",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /estabelecimentos/{id}/editar", "redirect")
        else:
            fail("POST /estabelecimentos/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/estabelecimentos/{eid}/desativar", follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /estabelecimentos/{id}/desativar", "redirect")
        else:
            fail("POST /estabelecimentos/{id}/desativar", f"status={r.status_code}")

    # ─── 10. PROFISSIONAIS CRUD ─────────────────────────────
    print("\n--- 10. PROFISSIONAIS CRUD ---")
    r = c.get("/profissionais")
    if r.status_code == 200:
        ok("GET /profissionais", "200")
    else:
        fail("GET /profissionais", f"status={r.status_code}")

    r = c.post("/profissionais/criar", data={
        "nome": "Dr. Teste Audit",
        "email": "dr_teste_audit@test.com",
        "senha": "test123",
        "especialidade": "Odontologia",
        "estabelecimento_id": str(estab_id),
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /profissionais/criar", "redirect")
    else:
        fail("POST /profissionais/criar", f"status={r.status_code}")

    dr = db.fetch_one("SELECT id FROM usuarios WHERE email = 'dr_teste_audit@test.com'")
    if dr:
        r = c.get(f"/profissionais/{dr['id']}/editar")
        if r.status_code == 200:
            ok("GET /profissionais/{id}/editar", "200")
        else:
            fail("GET /profissionais/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/profissionais/{dr['id']}/editar", data={
            "nome": "Dr. Teste Editado",
            "email": "dr_teste_audit@test.com",
            "especialidade": "Clinica Geral",
            "estabelecimento_id": str(estab_id),
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /profissionais/{id}/editar", "redirect")
        else:
            fail("POST /profissionais/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/profissionais/{dr['id']}/desativar", follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /profissionais/{id}/desativar", "redirect")
        else:
            fail("POST /profissionais/{id}/desativar", f"status={r.status_code}")
    else:
        fail("POST /profissionais/criar", "profissional nao criado")

    # ─── 11. PACIENTES CRUD ─────────────────────────────────
    print("\n--- 11. PACIENTES CRUD ---")
    r = c.get("/pacientes")
    if r.status_code == 200:
        ok("GET /pacientes", "200")
    else:
        fail("GET /pacientes", f"status={r.status_code}")

    r = c.post("/pacientes/criar", data={
        "nome": "Paciente Teste Audit",
        "email": "pac_teste_audit@test.com",
        "senha": "test123",
        "estabelecimento_id": str(estab_id),
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /pacientes/criar", "redirect")
    else:
        fail("POST /pacientes/criar", f"status={r.status_code}")

    pac2 = db.fetch_one("SELECT id FROM usuarios WHERE email = 'pac_teste_audit@test.com'")
    if pac2:
        r = c.get(f"/pacientes/{pac2['id']}/editar")
        if r.status_code == 200:
            ok("GET /pacientes/{id}/editar", "200")
        else:
            fail("GET /pacientes/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/pacientes/{pac2['id']}/editar", data={
            "nome": "Paciente Teste Editado",
            "email": "pac_teste_audit@test.com",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /pacientes/{id}/editar", "redirect")
        else:
            fail("POST /pacientes/{id}/editar", f"status={r.status_code}")

        # Paciente convenio page
        r = c.get(f"/pacientes/{pac2['id']}/convenio")
        if r.status_code == 200:
            ok("GET /pacientes/{id}/convenio", "200")
        else:
            fail("GET /pacientes/{id}/convenio", f"status={r.status_code}")
    else:
        fail("POST /pacientes/criar", "paciente nao criado")

    # ─── 12. CONVENIOS CRUD ─────────────────────────────────
    print("\n--- 12. CONVENIOS CRUD ---")
    r = c.get("/convenios")
    if r.status_code == 200:
        ok("GET /convenios", "200")
    else:
        fail("GET /convenios", f"status={r.status_code}")

    r = c.get("/convenios/novo")
    if r.status_code == 200:
        ok("GET /convenios/novo", "200")
    else:
        fail("GET /convenios/novo", f"status={r.status_code}")

    r = c.post("/convenios/criar", data={
        "nome": "Convenio Teste Audit",
        "cnpj": "12345678000199",
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /convenios/criar", "redirect")
    else:
        fail("POST /convenios/criar", f"status={r.status_code}")

    conv = db.fetch_one("SELECT id FROM convenios WHERE nome = 'Convenio Teste Audit'")
    if conv:
        r = c.get(f"/convenios/{conv['id']}/editar")
        if r.status_code == 200:
            ok("GET /convenios/{id}/editar", "200")
        else:
            fail("GET /convenios/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/convenios/{conv['id']}/editar", data={
            "nome": "Convenio Editado",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /convenios/{id}/editar", "redirect")
        else:
            fail("POST /convenios/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/convenios/{conv['id']}/desativar", follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /convenios/{id}/desativar", "redirect")
        else:
            fail("POST /convenios/{id}/desativar", f"status={r.status_code}")
    else:
        fail("POST /convenios/criar", "convenio nao criado")

    # ─── 13. PROCEDIMENTOS CRUD ─────────────────────────────
    print("\n--- 13. PROCEDIMENTOS CRUD ---")
    r = c.get("/procedimentos")
    if r.status_code == 200:
        ok("GET /procedimentos", "200")
    else:
        fail("GET /procedimentos", f"status={r.status_code}")

    r = c.get("/procedimentos/novo")
    if r.status_code == 200:
        ok("GET /procedimentos/novo", "200")
    else:
        fail("GET /procedimentos/novo", f"status={r.status_code}")

    r = c.post("/procedimentos/criar", data={
        "nome": "Procedimento Teste Audit",
        "descricao": "Teste",
        "duracao_minutos": "30",
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /procedimentos/criar", "redirect")
    else:
        fail("POST /procedimentos/criar", f"status={r.status_code}")

    proc = db.fetch_one("SELECT id FROM procedimentos WHERE nome = 'Procedimento Teste Audit'")
    if proc:
        r = c.get(f"/procedimentos/{proc['id']}/editar")
        if r.status_code == 200:
            ok("GET /procedimentos/{id}/editar", "200")
        else:
            fail("GET /procedimentos/{id}/editar", f"status={r.status_code}")

        r = c.post(f"/procedimentos/{proc['id']}/editar", data={
            "nome": "Procedimento Editado",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /procedimentos/{id}/editar", "redirect")
        else:
            fail("POST /procedimentos/{id}/editar", f"status={r.status_code}")

        r = c.get(f"/procedimentos/{proc['id']}/valores")
        if r.status_code == 200:
            ok("GET /procedimentos/{id}/valores", "200")
        else:
            fail("GET /procedimentos/{id}/valores", f"status={r.status_code}")

        r = c.post(f"/procedimentos/{proc['id']}/valores/salvar", data={
            "valor_particular": "150.00",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /procedimentos/{id}/valores/salvar", "redirect")
        else:
            fail("POST /procedimentos/{id}/valores/salvar", f"status={r.status_code}")

        r = c.post(f"/procedimentos/{proc['id']}/desativar", follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /procedimentos/{id}/desativar", "redirect")
        else:
            fail("POST /procedimentos/{id}/desativar", f"status={r.status_code}")
    else:
        fail("POST /procedimentos/criar", "procedimento nao criado")

    # ─── 14. APIs ───────────────────────────────────────────
    print("\n--- 14. APIs ---")
    r = c.get("/api/profissionais")
    if r.status_code == 200:
        ok("GET /api/profissionais", "200")
    else:
        fail("GET /api/profissionais", f"status={r.status_code}")

    r = c.get("/api/pacientes")
    if r.status_code == 200:
        ok("GET /api/pacientes", "200")
    else:
        fail("GET /api/pacientes", f"status={r.status_code}")

    r = c.get("/api/procedimentos")
    if r.status_code == 200:
        ok("GET /api/procedimentos", "200")
    else:
        fail("GET /api/procedimentos", f"status={r.status_code}")

    # Re-create convenio and proc for remaining tests
    db.execute("INSERT INTO convenios (nome) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", ("Conv Para Testes",))
    conv = db.fetch_one("SELECT id FROM convenios WHERE nome = 'Conv Para Testes'")
    conv_id = conv["id"] if conv else None

    db.execute("INSERT INTO procedimentos (nome) VALUES (%s) ON DUPLICATE KEY UPDATE id=id", ("Proc Para Testes",))
    proc = db.fetch_one("SELECT id FROM procedimentos WHERE nome = 'Proc Para Testes'")
    proc_id = proc["id"] if proc else None

    if conv_id and proc_id:
        r = c.get(f"/api/convenios-paciente?paciente_id={pac_id}")
        if r.status_code == 200:
            ok("GET /api/convenios-paciente", "200")
        else:
            fail("GET /api/convenios-paciente", f"status={r.status_code}")

        r = c.get(f"/api/procedimento-valor?procedimento_id={proc_id}")
        if r.status_code == 200:
            ok("GET /api/procedimento-valor", "200")
        else:
            fail("GET /api/procedimento-valor", f"status={r.status_code}")

    # ─── 15. CONSULTAS ──────────────────────────────────────
    print("\n--- 15. CONSULTAS ---")
    r = c.get("/consultas")
    if r.status_code == 200:
        ok("GET /consultas", "200")
    else:
        fail("GET /consultas", f"status={r.status_code}")

    r = c.get("/consultas/nova")
    if r.status_code == 200:
        ok("GET /consultas/nova", "200")
    else:
        fail("GET /consultas/nova", f"status={r.status_code}")

    r = c.get("/api/consultas?inicio=2026-01-01&fim=2026-12-31")
    if r.status_code == 200:
        ok("GET /api/consultas", "200")
    else:
        fail("GET /api/consultas", f"status={r.status_code}")

    r = c.post("/consultas/criar", data={
        "paciente_id": str(pac_id),
        "profissional_id": str(prof_id),
        "data_hora": "2026-07-25 10:00",
        "duracao": "30",
        "estabelecimento_id": str(estab_id),
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /consultas/criar", "redirect")
    else:
        fail("POST /consultas/criar", f"status={r.status_code}")

    cons = db.fetch_one("SELECT id FROM consultas ORDER BY id DESC LIMIT 1")
    if cons:
        r = c.post(f"/consultas/{cons['id']}/status", data={"status": "confirmada"}, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /consultas/{id}/status", "redirect")
        else:
            fail("POST /consultas/{id}/status", f"status={r.status_code}")
    else:
        fail("POST /consultas/criar", "consulta nao criada")

    # ─── 16. PRONTUARIOS ────────────────────────────────────
    print("\n--- 16. PRONTUARIOS (TESTE CRITICO) ---")
    r = c.get("/prontuarios")
    if r.status_code == 200:
        ok("GET /prontuarios", "200")
    else:
        fail("GET /prontuarios", f"status={r.status_code}")

    print(f"  DEBUG: pac_id={pac_id}, estab_id={estab_id}")
    print(f"  DEBUG: Verificando paciente_estabelecimento...")
    pe = db.fetch_one("SELECT * FROM paciente_estabelecimento WHERE usuario_id = %s AND estabelecimento_id = %s", (pac_id, estab_id))
    print(f"  DEBUG: paciente_estabelecimento = {pe}")

    r = c.post("/prontuarios/criar", data={
        "paciente_id": str(pac_id),
        "estabelecimento_id": str(estab_id),
    }, follow_redirects=False)
    print(f"  POST /prontuarios/criar -> status={r.status_code}, location={r.headers.get('location', 'N/A')}")
    if r.status_code in (302, 307):
        ok("POST /prontuarios/criar", f"redirect -> {r.headers.get('location', '')}")
    else:
        fail("POST /prontuarios/criar", f"status={r.status_code} body={r.text[:200]}")

    prat = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s", (pac_id, estab_id))
    if prat:
        r = c.get(f"/prontuarios/{prat['id']}")
        if r.status_code == 200:
            ok("GET /prontuarios/{id}", "200")
        else:
            fail("GET /prontuarios/{id}", f"status={r.status_code}")

        # Evolucao
        r = c.post(f"/prontuarios/{prat['id']}/evolucao", data={
            "profissional_id": str(prof_id),
            "queixa": "Dor de dente",
            "diagnostico": "Caries",
            "procedimento": "Restauracao",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /prontuarios/{id}/evolucao", "redirect")
        else:
            fail("POST /prontuarios/{id}/evolucao", f"status={r.status_code}")

        evo = db.fetch_one("SELECT id FROM evolucoes WHERE prontuario_id = %s ORDER BY id DESC LIMIT 1", (prat["id"],))
        if evo:
            # Tratamento
            r = c.post(f"/prontuarios/{prat['id']}/evolucao/{evo['id']}/tratamento", data={
                "tipo": "Restauracao",
                "descricao": "Restauracao em dente 36",
                "dente": "36",
                "face": "oclusal",
                "material": "Amalgama",
                "valor": "250.00",
            }, follow_redirects=False)
            if r.status_code in (302, 307):
                ok("POST /prontuarios/{id}/evolucao/{id}/tratamento", "redirect")
            else:
                fail("POST /prontuarios/{id}/evolucao/{id}/tratamento", f"status={r.status_code}")
        else:
            fail("POST /prontuarios/{id}/evolucao", "evolucao nao criada")
    else:
        fail("POST /prontuarios/criar", "PRONTUARIO NAO CRIADO - VERIFICAR DB")

    # ─── 17. AGENDA ─────────────────────────────────────────
    print("\n--- 17. AGENDA ---")
    r = c.get("/agenda")
    if r.status_code == 200:
        ok("GET /agenda", "200")
    else:
        fail("GET /agenda", f"status={r.status_code}")

    # ─── 18. ORCAMENTOS ─────────────────────────────────────
    print("\n--- 18. ORCAMENTOS ---")
    r = c.get("/orcamentos")
    if r.status_code == 200:
        ok("GET /orcamentos", "200")
    else:
        fail("GET /orcamentos", f"status={r.status_code}")

    r = c.get("/orcamentos/novo")
    if r.status_code == 200:
        ok("GET /orcamentos/novo", "200")
    else:
        fail("GET /orcamentos/novo", f"status={r.status_code}")

    r = c.post("/orcamentos/criar", data={
        "paciente_id": str(pac_id),
        "profissional_id": str(prof_id),
        "estabelecimento_id": str(estab_id),
    }, follow_redirects=False)
    if r.status_code in (302, 307):
        ok("POST /orcamentos/criar", f"redirect -> {r.headers.get('location', '')}")
    else:
        fail("POST /orcamentos/criar", f"status={r.status_code}")

    orc = db.fetch_one("SELECT id FROM orcamentos ORDER BY id DESC LIMIT 1")
    if orc:
        r = c.get(f"/orcamentos/{orc['id']}")
        if r.status_code == 200:
            ok("GET /orcamentos/{id}", "200")
        else:
            fail("GET /orcamentos/{id}", f"status={r.status_code}")

        # Adicionar item
        r = c.post(f"/orcamentos/{orc['id']}/item/adicionar", data={
            "descricao": "Procedimento Teste",
            "quantidade": "1",
            "valor_unitario": "100.00",
            "desconto": "0",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /orcamentos/{id}/item/adicionar", "redirect")
        else:
            fail("POST /orcamentos/{id}/item/adicionar", f"status={r.status_code}")

        item = db.fetch_one("SELECT id FROM orcamento_itens WHERE orcamento_id = %s LIMIT 1", (orc["id"],))
        if item:
            r = c.post(f"/orcamentos/{orc['id']}/item/{item['id']}/remover", follow_redirects=False)
            if r.status_code in (302, 307):
                ok("POST /orcamentos/{id}/item/{id}/remover", "redirect")
            else:
                fail("POST /orcamentos/{id}/item/{id}/remover", f"status={r.status_code}")

        # Re-add item for further tests
        c.post(f"/orcamentos/{orc['id']}/item/adicionar", data={
            "descricao": "Procedimento Teste",
            "quantidade": "1",
            "valor_unitario": "100.00",
        })

        # Status
        r = c.post(f"/orcamentos/{orc['id']}/status", data={"status": "enviado"}, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /orcamentos/{id}/status", "redirect")
        else:
            fail("POST /orcamentos/{id}/status", f"status={r.status_code}")

        # Imprimir
        r = c.get(f"/orcamentos/{orc['id']}/imprimir")
        if r.status_code == 200:
            ok("GET /orcamentos/{id}/imprimir", "200")
        else:
            fail("GET /orcamentos/{id}/imprimir", f"status={r.status_code}")

        # Pagina de pagamento
        r = c.get(f"/orcamentos/{orc['id']}/pagar")
        if r.status_code == 200:
            ok("GET /orcamentos/{id}/pagar", "200")
        else:
            fail("GET /orcamentos/{id}/pagar", f"status={r.status_code}")

        # Registrar pagamento
        r = c.post(f"/orcamentos/{orc['id']}/pagar", data={
            "valor": "100.00",
            "metodo": "pix",
            "parcelas": "1",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /orcamentos/{id}/pagar (registrar)", "redirect")
        else:
            fail("POST /orcamentos/{id}/pagar (registrar)", f"status={r.status_code}")

        # Cancelar pagamento
        pag = db.fetch_one("SELECT id FROM pagamentos WHERE orcamento_id = %s LIMIT 1", (orc["id"],))
        if pag:
            r = c.post(f"/orcamentos/{orc['id']}/pagamento/{pag['id']}/cancelar", follow_redirects=False)
            if r.status_code in (302, 307):
                ok("POST /orcamentos/{id}/pagamento/{id}/cancelar", "redirect")
            else:
                fail("POST /orcamentos/{id}/pagamento/{id}/cancelar", f"status={r.status_code}")

        # Nota fiscal
        r = c.get(f"/orcamentos/{orc['id']}/nota-fiscal")
        if r.status_code == 200:
            ok("GET /orcamentos/{id}/nota-fiscal", "200")
        else:
            fail("GET /orcamentos/{id}/nota-fiscal", f"status={r.status_code}")

        # Converter para consulta
        r = c.post(f"/orcamentos/{orc['id']}/converter", data={
            "data_hora": "2026-08-01 14:00",
            "duracao": "30",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /orcamentos/{id}/converter", "redirect")
        else:
            fail("POST /orcamentos/{id}/converter", f"status={r.status_code}")
    else:
        fail("POST /orcamentos/criar", "orcamento nao criado")

    # ─── 19. PACIENTE CONVENIO ──────────────────────────────
    print("\n--- 19. PACIENTE CONVENIO ---")
    if conv_id:
        r = c.post(f"/pacientes/{pac_id}/convenio/salvar", data={
            "convenio_id": str(conv_id),
            "numero_carteirinha": "12345",
        }, follow_redirects=False)
        if r.status_code in (302, 307):
            ok("POST /pacientes/{id}/convenio/salvar", "redirect")
        else:
            fail("POST /pacientes/{id}/convenio/salvar", f"status={r.status_code}")

        vc = db.fetch_one("SELECT id FROM paciente_convenio WHERE paciente_usuario_id = %s AND convenio_id = %s", (pac_id, conv_id))
        if vc:
            r = c.post(f"/pacientes/{pac_id}/convenio/{vc['id']}/remover", follow_redirects=False)
            if r.status_code in (302, 307):
                ok("POST /pacientes/{id}/convenio/{id}/remover", "redirect")
            else:
                fail("POST /pacientes/{id}/convenio/{id}/remover", f"status={r.status_code}")

    # ─── 20. FINANCEIRO E PAGAMENTOS ────────────────────────
    print("\n--- 20. FINANCEIRO E PAGAMENTOS ---")
    r = c.get("/financeiro")
    if r.status_code == 200:
        ok("GET /financeiro", "200")
    else:
        fail("GET /financeiro", f"status={r.status_code}")

    r = c.get("/pagamentos")
    if r.status_code == 200:
        ok("GET /pagamentos", "200")
    else:
        fail("GET /pagamentos", f"status={r.status_code}")

    # ─── 21. UPLOAD ─────────────────────────────────────────
    print("\n--- 21. UPLOAD ---")
    import io
    upload_file = io.BytesIO(b"fake image content")
    r = c.post("/api/upload", files={"arquivo": ("test.png", upload_file, "image/png")})
    if r.status_code == 200:
        ok("POST /api/upload", "200")
    else:
        fail("POST /api/upload", f"status={r.status_code}")

    # ─── 22. TESTES DE NEGACAO (sem login) ──────────────────
    print("\n--- 22. NEGACAO: SEM LOGIN ---")
    c3 = TestClient(app, raise_server_exceptions=False)
    denied_routes = [
        ("GET", "/dashboard"),
        ("GET", "/pacientes"),
        ("GET", "/consultas"),
        ("GET", "/prontuarios"),
        ("GET", "/orcamentos"),
        ("GET", "/convenios"),
        ("GET", "/procedimentos"),
        ("GET", "/agenda"),
        ("GET", "/financeiro"),
        ("GET", "/pagamentos"),
        ("GET", "/admin/cupons"),
        ("GET", "/estabelecimentos"),
        ("GET", "/profissionais"),
    ]
    for method, route in denied_routes:
        r = c3.get(route)
        if r.status_code in (302, 307, 403):
            ok(f"{method} {route} (sem login)", f"status={r.status_code} bloqueado")
        elif r.status_code == 200 and "login" in r.text.lower():
            ok(f"{method} {route} (sem login)", "redirecionou para login no HTML")
        else:
            fail(f"{method} {route} (sem login)", f"status={r.status_code} DEVERIA BLOQUEAR")

    # ─── RESUMO ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    total = PASSADOS + FALHADOS
    print(f"RESULTADO: {PASSADOS}/{total} passaram, {FALHADOS} falharam")
    if ERROS:
        print("\nFALHAS DETALHADAS:")
        for route, msg in ERROS:
            print(f"  x {route}: {msg}")
    print("=" * 70)
    return FALHADOS == 0


if __name__ == "__main__":
    success = test_rotas()
    db.get_connection()
    db.execute("SET FOREIGN_KEY_CHECKS = 0")
    for t in ['tratamentos', 'evolucoes', 'imaging', 'consultas', 'prontuarios',
              'paciente_estabelecimento', 'profissional_estabelecimento', 'permissoes_paciente',
              'permissoes_usuario', 'log_atividades', 'estoque', 'procedimento_valor', 'paciente_convenio',
              'orcamento_itens', 'orcamentos', 'pagamentos', 'odontograma', 'sync_meta']:
        db.execute(f"DELETE FROM {t}")
    db.execute("DELETE FROM usuarios WHERE id > 1")
    db.execute("DELETE FROM estabelecimentos")
    db.execute("DELETE FROM convenios")
    db.execute("DELETE FROM procedimentos")
    db.execute("DELETE FROM cupons")
    db.execute("ALTER TABLE usuarios AUTO_INCREMENT = 2")
    db.execute("ALTER TABLE estabelecimentos AUTO_INCREMENT = 1")
    db.execute("INSERT INTO estabelecimentos (id, nome, tipo, ativo) VALUES (1, 'Clinica IDOR', 'clinica', TRUE)")
    db.execute("INSERT IGNORE INTO profissional_estabelecimento (usuario_id, estabelecimento_id) VALUES (1, 1)")
    db.execute("INSERT IGNORE INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (2, 1), (3, 1)")
    db.execute("SET FOREIGN_KEY_CHECKS = 1")
    db.close()
    sys.exit(0 if success else 1)
