"""
TESTE COMPLETO: Controle de acesso a prontuarios multi-estabelecimento
======================================================================
Cenario:
  - Clinica Odonto (estab 1): Dra. Ana (prof), Dra. Beatriz (prof)
  - Hospital Saude (estab 2): Dr. Carlos (prof), Dra. Diana (prof)
  - Pacientes:
    - Maria (email: maria@email.com) -> consulta com Dra. Ana em Clinica Odonto
    - Pedro (email: pedro@email.com) -> consulta com Dra. Ana E Dra. Beatriz em Clinica Odonto
    - Joao (email: joao_pac@email.com) -> consulta com Dr. Carlos em Hospital Saude
    - Pai (email: familia@email.com) -> consulta com Dra. Ana em Clinica Odonto
    - Filho (email: familia@email.com) -> consulta com Dra. Beatriz em Clinica Odonto
    - Ana (email: ana@email.com) -> consulta com Dr. Carlos em Hospital Saude E Dra. Ana em Clinica Odonto
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from main import app
from starlette.testclient import TestClient
from database.connection import db

errors = []
ok_count = 0

def check(name, condition, detail=""):
    global ok_count
    if condition:
        ok_count += 1
        print(f"  [OK] {name}{(' - ' + detail) if detail else ''}")
    else:
        errors.append(name)
        print(f"  [FALHOU] {name}{(' - ' + detail) if detail else ''}")

def contains_prontuario_row(html, nome):
    """Verifica se um nome aparece como paciente em uma row de prontuario (nao no dropdown de filtro)."""
    return f'data-prontuario-paciente="{nome}"' in html or f'pront-{nome.lower().replace(" ", "-")}' in html.lower()

client = TestClient(app, raise_server_exceptions=False)

print("=" * 70)
print("TESTE DE CONTROLE DE ACESSO A PRONTUARIOS")
print("=" * 70)

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
db.execute("SET FOREIGN_KEY_CHECKS = 1")

# ====================================================================
# SETUP: Limpar banco
# ====================================================================
print("\n--- 0. SETUP: Limpando banco ---")
db.execute("SET FOREIGN_KEY_CHECKS = 0")
for t in ['tratamentos', 'evolucoes', 'imaging', 'consultas', 'prontuarios',
          'paciente_estabelecimento', 'profissional_estabelecimento', 'permissoes_paciente',
          'log_atividades', 'estoque', 'procedimento_valor', 'paciente_convenio',
          'orcamento_itens', 'orcamentos', 'pagamentos']:
    db.execute(f"DELETE FROM {t}")
db.execute("DELETE FROM usuarios WHERE id > 1")
db.execute("DELETE FROM estabelecimentos")
db.execute("DELETE FROM convenios")
db.execute("DELETE FROM procedimentos")
db.execute("SET FOREIGN_KEY_CHECKS = 1")

for table, start in [('usuarios', 1), ('estabelecimentos', 1), ('consultas', 1), ('prontuarios', 1)]:
    try:
        db.execute(f"ALTER TABLE {table} AUTO_INCREMENT = {start}")
    except:
        pass

try:
    db.execute("ALTER TABLE usuarios DROP INDEX email")
    print("  UNIQUE constraint removido do email")
except:
    print("  UNIQUE constraint ja removido")

# ====================================================================
# SETUP: Login como super admin
# ====================================================================
print("\n--- 1. SETUP: Login super admin ---")
r = client.post("/login", data={"email": "marcusodontocotta@gmail.com", "senha": "admin123"})
check("Login super admin", r.status_code in (200, 302))

# ====================================================================
# SETUP: Criar estabelecimentos
# ====================================================================
print("\n--- 2. SETUP: Criando estabelecimentos ---")

r = client.post("/estabelecimentos/criar", data={
    "nome": "Clinica Odonto Total", "tipo": "clinica", "cnpj": "11.111.111/0001-11",
    "telefone": "(11) 99999-0001", "email": "contato@odontototal.com", "endereco": "Rua A, 100"
})
check("Criar Clinica Odonto", r.status_code in (200, 302))

r = client.post("/estabelecimentos/criar", data={
    "nome": "Hospital Saude Plena", "tipo": "hospital", "cnpj": "22.222.222/0001-22",
    "telefone": "(11) 99999-0002", "email": "contato@saudeplena.com", "endereco": "Rua B, 200"
})
check("Criar Hospital Saude", r.status_code in (200, 302))

estabs = db.fetch_all("SELECT id, nome FROM estabelecimentos ORDER BY id")
check("2 estabelecimentos criados", len(estabs) == 2, f"encontrados={len(estabs)}")
estab1_id = estabs[0]["id"]
estab2_id = estabs[1]["id"]
print(f"    Estab 1 (Odonto): ID={estab1_id}, Estab 2 (Hospital): ID={estab2_id}")

# ====================================================================
# SETUP: Criar profissionais
# ====================================================================
print("\n--- 3. SETUP: Criando profissionais ---")

profissionais = [
    ("dra_ana@email.com", "Dra. Ana", estab1_id),
    ("dra_beatriz@email.com", "Dra. Beatriz", estab1_id),
    ("dr_carlos@email.com", "Dr. Carlos", estab2_id),
    ("dra_diana@email.com", "Dra. Diana", estab2_id),
]
prof_ids = {}
for email, nome, estab in profissionais:
    r = client.post("/profissionais/criar", data={
        "nome": nome, "email": email, "senha": "123456",
        "especialidade": "Odontologia", "cargo": "Dentista",
        "telefone": "(11) 98888-0000", "estabelecimento_id": estab
    })
    check(f"Criar {nome}", r.status_code in (200, 302))
    u = db.fetch_one("SELECT id FROM usuarios WHERE email = %s", (email,))
    prof_ids[email] = u["id"]
    print(f"    {nome} (ID={u['id']}, estab={estab})")

# Criar recepcionista na Clinica Odonto (via DB direto pois criar_profissional hardcodes tipo=profissional)
from utils.auth import hash_senha
recep_hash = hash_senha("123456")
db.execute(
    "INSERT INTO usuarios (nome, email, senha_hash, tipo, ativo) VALUES (%s, %s, %s, %s, TRUE)",
    ("Joao Recep", "joao_recep@email.com", recep_hash, "recepcionista")
)
recep_id = db.fetch_one("SELECT id FROM usuarios WHERE email = 'joao_recep@email.com'")["id"]
db.execute(
    "INSERT INTO profissional_estabelecimento (usuario_id, estabelecimento_id, cargo) VALUES (%s, %s, %s)",
    (recep_id, estab1_id, "Recepcionista")
)
recep_tipo = db.fetch_one("SELECT id, tipo FROM usuarios WHERE email = 'joao_recep@email.com'")
check("Criar Joao Recep", recep_id is not None)
print(f"    Joao Recep (ID={recep_id}, tipo={recep_tipo['tipo']}, estab={estab1_id})")

# Criar admin para Clinica Odonto (via DB direto)
admin_hash = hash_senha("123456")
db.execute(
    "INSERT INTO usuarios (nome, email, senha_hash, tipo, ativo) VALUES (%s, %s, %s, %s, TRUE)",
    ("Admin Odonto", "admin_odonto@email.com", admin_hash, "admin")
)
admin_odonto_id = db.fetch_one("SELECT id FROM usuarios WHERE email = 'admin_odonto@email.com'")["id"]
check("Criar admin Clinica Odonto", admin_odonto_id is not None)
admin_odonto = db.fetch_one("SELECT id, tipo FROM usuarios WHERE email = 'admin_odonto@email.com'")
print(f"    Admin Odonto (ID={admin_odonto_id}, tipo={admin_odonto['tipo']})")

# ====================================================================
# SETUP: Criar pacientes
# ====================================================================
print("\n--- 4. SETUP: Criando pacientes ---")

pacientes = [
    ("maria@email.com", "Maria Silva", estab1_id),
    ("pedro@email.com", "Pedro Santos", estab1_id),
    ("joao_pac@email.com", "Joao Oliveira", estab2_id),
    ("familia@email.com", "Pai Ferreira", estab1_id),
    ("familia@email.com", "Filho Ferreira", estab1_id),
    ("ana@email.com", "Ana Costa", estab2_id),
    ("ana@email.com", "Ana Costa Dupla", estab1_id),
]
pac_ids = {}
for email, nome, estab in pacientes:
    r = client.post("/pacientes/criar", data={
        "nome": nome, "email": email, "senha": "123456",
        "telefone": "(11) 96666-0000", "estabelecimento_id": estab
    })
    check(f"Criar {nome}", r.status_code in (200, 302))
    u = db.fetch_one("SELECT id FROM usuarios WHERE email = %s AND nome = %s", (email, nome))
    if u:
        pac_ids[nome] = u["id"]
        print(f"    {nome} (ID={u['id']}, email={email}, estab={estab})")
    else:
        pac_ids[nome] = None
        print(f"    {nome} (FALHA ao buscar)")

familia_users = db.fetch_all("SELECT id, nome FROM usuarios WHERE email = 'familia@email.com'")
check("Email duplicado: 2 usuarios com familia@email.com", len(familia_users) == 2,
      f"encontrados={len(familia_users)}")

ana_users = db.fetch_all("SELECT id, nome FROM usuarios WHERE email = 'ana@email.com'")
check("Email duplicado: 2 usuarios com ana@email.com", len(ana_users) == 2,
      f"encontrados={len(ana_users)}")

# Verificar vinculos paciente_estabelecimento
pe_count = db.fetch_all("SELECT pe.usuario_id, pe.estabelecimento_id, u.nome FROM paciente_estabelecimento pe JOIN usuarios u ON u.id = pe.usuario_id ORDER BY u.nome")
print(f"    Vinculos paciente_estabelecimento: {len(pe_count)}")
for v in pe_count:
        print(f"      {v['nome']} -> estab {v['estabelecimento_id']}")

# ====================================================================
# SETUP: Criar consultas
# ====================================================================
print("\n--- 5. SETUP: Criando consultas ---")

consultas = [
    ("Maria Silva", "dra_ana@email.com", estab1_id, "2026-07-20 10:00:00"),
    ("Pedro Santos", "dra_ana@email.com", estab1_id, "2026-07-21 10:00:00"),
    ("Pedro Santos", "dra_beatriz@email.com", estab1_id, "2026-07-22 10:00:00"),
    ("Joao Oliveira", "dr_carlos@email.com", estab2_id, "2026-07-23 10:00:00"),
    ("Pai Ferreira", "dra_ana@email.com", estab1_id, "2026-07-24 10:00:00"),
    ("Filho Ferreira", "dra_beatriz@email.com", estab1_id, "2026-07-24 14:00:00"),
    ("Ana Costa", "dr_carlos@email.com", estab2_id, "2026-07-25 10:00:00"),
    ("Ana Costa Dupla", "dra_ana@email.com", estab1_id, "2026-07-25 14:00:00"),
]
for pac_nome, prof_email, estab, data in consultas:
    pac_id = pac_ids.get(pac_nome)
    prof_id = prof_ids.get(prof_email)
    if pac_id and prof_id:
        r = client.post("/consultas/criar", data={
            "paciente_id": pac_id, "profissional_id": prof_id,
            "data_hora": data, "duracao": 30, "estabelecimento_id": estab
        })
        check(f"Consulta {pac_nome} <-> {prof_email.split('@')[0]} em estab {estab}",
              r.status_code in (200, 302))
    else:
        check(f"Consulta {pac_nome} <-> {prof_email}", False,
              f"pac_id={pac_id}, prof_id={prof_id}")

consultas_db = db.fetch_all("SELECT COUNT(*) as cnt FROM consultas")
print(f"    Total consultas criadas: {consultas_db[0]['cnt']}")

# ====================================================================
# SETUP: Criar prontuarios (via direto no DB)
# ====================================================================
print("\n--- 6. SETUP: Criando prontuarios ---")

prontuarios_criar = [
    ("Maria Silva", estab1_id),
    ("Pedro Santos", estab1_id),
    ("Joao Oliveira", estab2_id),
    ("Pai Ferreira", estab1_id),
    ("Filho Ferreira", estab1_id),
    ("Ana Costa", estab2_id),
    ("Ana Costa Dupla", estab1_id),
]
pront_ids = {}
for pac_nome, estab in prontuarios_criar:
    pac_id = pac_ids.get(pac_nome)
    if pac_id:
        try:
            db.execute(
                "INSERT INTO prontuarios (paciente_usuario_id, estabelecimento_id, numero_prontuario) VALUES (%s, %s, %s)",
                (pac_id, estab, f"PRONT-{pac_nome[:3].upper()}-{estab}")
            )
            p = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s AND estabelecimento_id = %s",
                           (pac_id, estab))
            if p:
                pront_ids[pac_nome] = p["id"]
                check(f"Prontuario {pac_nome} (estab {estab})", True, f"ID={p['id']}")
            else:
                check(f"Prontuario {pac_nome} (estab {estab})", False, "Nao encontrado apos INSERT")
        except Exception as e:
            check(f"Prontuario {pac_nome} (estab {estab})", False, str(e))
    else:
        check(f"Prontuario {pac_nome}", False, "pac_id nao encontrado")

# ====================================================================
# HELPER: Buscar ids dos prontuarios da listagem HTML
# ====================================================================
def parse_prontuario_ids(html):
    """Extrai IDs de prontuarios da listagem HTML"""
    import re
    ids = set()
    for m in re.finditer(r'/prontuarios/(\d+)', html):
        ids.add(int(m.group(1)))
    return ids

# ====================================================================
# TESTES: Acesso da Dra. Ana (Clinica Odonto)
# ====================================================================
print("\n--- 7. TESTE: Acesso da Dra. Ana (Clinica Odonto) ---")

r = client.post("/login", data={"email": "dra_ana@email.com", "senha": "123456"})
check("Login Dra. Ana", r.status_code in (200, 302))
estab_cookie = client.cookies.get("estabelecimento_id")
check("Cookie estabelecimento_id setado", estab_cookie is not None, f"cookie={estab_cookie}")

r = client.get("/prontuarios")
check("Dra. Ana: GET /prontuarios", r.status_code == 200)
html = r.text
pront_ids_html = parse_prontuario_ids(html)

# Dra. Ana atendeu: Maria(1), Pedro(2), Pai(4), Ana Costa Dupla(7)
# NAO atendeu: Filho(5), Joao(3), Ana Costa(6)
check("Dra. Ana ve prontuario Maria", 1 in pront_ids_html)
check("Dra. Ana ve prontuario Pedro", 2 in pront_ids_html)
check("Dra. Ana ve prontuario Pai Ferreira", 4 in pront_ids_html)
check("Dra. Ana ve prontuario Ana Costa Dupla", 7 in pront_ids_html)
check("Dra. Ana NAO ve prontuario Filho", 5 not in pront_ids_html,
      "Filho foi atendido pela Dra. Beatriz")
check("Dra. Ana NAO ve prontuario Joao", 3 not in pront_ids_html,
      "Joao esta em Hospital Saude")
check("Dra. Ana NAO ve prontuario Ana Costa", 6 not in pront_ids_html,
      "Ana Costa esta em Hospital Saude")

# Acesso individual - seu paciente (OK)
if pront_ids.get("Maria Silva"):
    r = client.get(f"/prontuarios/{pront_ids['Maria Silva']}")
    check("Dra. Ana acessa prontuario Maria (seu paciente)", r.status_code == 200)

if pront_ids.get("Pedro Santos"):
    r = client.get(f"/prontuarios/{pront_ids['Pedro Santos']}")
    check("Dra. Ana acessa prontuario Pedro (seu paciente)", r.status_code == 200)

# Acesso individual - paciente de outra profissional (BLOQUEADO)
if pront_ids.get("Filho Ferreira"):
    r = client.get(f"/prontuarios/{pront_ids['Filho Ferreira']}")
    check("Dra. Ana BLOQUEADA de prontuario Filho (paciente nao e dela)",
          r.status_code == 403, f"status={r.status_code}")

# Acesso individual - outro estabelecimento (BLOQUEADO)
if pront_ids.get("Joao Oliveira"):
    r = client.get(f"/prontuarios/{pront_ids['Joao Oliveira']}")
    check("Dra. Ana BLOQUEADA de prontuario Joao (outro estabelecimento)",
          r.status_code == 403, f"status={r.status_code}")

# ====================================================================
# TESTES: Acesso da Dra. Beatriz (Clinica Odonto)
# ====================================================================
print("\n--- 8. TESTE: Acesso da Dra. Beatriz (Clinica Odonto) ---")

r = client.post("/login", data={"email": "dra_beatriz@email.com", "senha": "123456"})
check("Login Dra. Beatriz", r.status_code in (200, 302))
estab_cookie = client.cookies.get("estabelecimento_id")
check("Cookie estabelecimento_id setado (Beatriz)", estab_cookie is not None, f"cookie={estab_cookie}")

r = client.get("/prontuarios")
html = r.text
pront_ids_html = parse_prontuario_ids(html)

# Beatriz atendeu: Pedro(2), Filho(5)
check("Dra. Beatriz ve prontuario Pedro", 2 in pront_ids_html)
check("Dra. Beatriz ve prontuario Filho Ferreira", 5 in pront_ids_html)
check("Dra. Beatriz NAO ve prontuario Maria", 1 not in pront_ids_html,
      "Maria so foi atendida pela Dra. Ana")
check("Dra. Beatriz NAO ve prontuario Pai Ferreira", 4 not in pront_ids_html,
      "Pai so foi atendido pela Dra. Ana")
check("Dra. Beatriz NAO ve prontuario Ana Costa Dupla", 7 not in pront_ids_html,
      "Ana Costa Dupla so foi atendida pela Dra. Ana")

# Acesso individual: BLOQUEADA de paciente que nao atendeu
if pront_ids.get("Maria Silva"):
    r = client.get(f"/prontuarios/{pront_ids['Maria Silva']}")
    check("Dra. Beatriz BLOQUEADA de prontuario Maria (nao atendeu)",
          r.status_code == 403, f"status={r.status_code}")

if pront_ids.get("Pai Ferreira"):
    r = client.get(f"/prontuarios/{pront_ids['Pai Ferreira']}")
    check("Dra. Beatriz BLOQUEADA de prontuario Pai (nao atendeu)",
          r.status_code == 403, f"status={r.status_code}")

# Acesso individual: ACESSA seus pacientes
if pront_ids.get("Filho Ferreira"):
    r = client.get(f"/prontuarios/{pront_ids['Filho Ferreira']}")
    check("Dra. Beatriz acessa prontuario Filho (seu paciente)", r.status_code == 200)

if pront_ids.get("Pedro Santos"):
    r = client.get(f"/prontuarios/{pront_ids['Pedro Santos']}")
    check("Dra. Beatriz acessa prontuario Pedro (compartilhado)", r.status_code == 200)

# ====================================================================
# TESTES: Acesso do Dr. Carlos (Hospital Saude)
# ====================================================================
print("\n--- 9. TESTE: Acesso do Dr. Carlos (Hospital Saude) ---")

r = client.post("/login", data={"email": "dr_carlos@email.com", "senha": "123456"})
check("Login Dr. Carlos", r.status_code in (200, 302))
estab_cookie = client.cookies.get("estabelecimento_id")
check("Cookie estabelecimento_id setado (Carlos)", estab_cookie is not None, f"cookie={estab_cookie}")

r = client.get("/prontuarios")
html = r.text
pront_ids_html = parse_prontuario_ids(html)

check("Dr. Carlos ve prontuario Joao", 3 in pront_ids_html)
check("Dr. Carlos ve prontuario Ana Costa", 6 in pront_ids_html)
check("Dr. Carlos NAO ve prontuario Maria", 1 not in pront_ids_html)
check("Dr. Carlos NAO ve prontuario Pedro", 2 not in pront_ids_html)
check("Dr. Carlos NAO ve prontuario Pai Ferreira", 4 not in pront_ids_html)

# Acesso individual
if pront_ids.get("Maria Silva"):
    r = client.get(f"/prontuarios/{pront_ids['Maria Silva']}")
    check("Dr. Carlos BLOQUEADO de prontuario Maria (outro estab)", r.status_code == 403)

if pront_ids.get("Joao Oliveira"):
    r = client.get(f"/prontuarios/{pront_ids['Joao Oliveira']}")
    check("Dr. Carlos acessa prontuario Joao (seu paciente)", r.status_code == 200)

# ====================================================================
# TESTES: Email duplicado - API verificar-email
# ====================================================================
print("\n--- 10. TESTE: Email duplicado - API verificar-email ---")

r = client.post("/login", data={"email": "marcusodontocotta@gmail.com", "senha": "admin123"})
check("Login super admin para API", r.status_code in (200, 302))
client.cookies.set("estabelecimento_id", str(estab1_id))

r = client.get("/api/verificar-email?email=familia@email.com")
check("API verificar-email familia@email.com", r.status_code == 200)
data = r.json()
check("API retorna existe=True", data["existe"] is True)
check("API retorna 2 pacientes", len(data["pacientes"]) == 2,
      f"encontrados={len(data['pacientes'])}: {[p['nome'] for p in data['pacientes']]}")
for p in data["pacientes"]:
    check(f"  {p['nome']} tem prontuarios", len(p["prontuarios"]) > 0,
          f"qtd={len(p['prontuarios'])}")
    check(f"  {p['nome']} pode_acessar=True", p["pode_acessar"] is True)

r = client.get("/api/verificar-email?email=maria@email.com")
data = r.json()
check("API verificar-email maria@email.com retorna 1 paciente", len(data["pacientes"]) == 1)

r = client.get("/api/verificar-email?email=naoexiste@email.com")
data = r.json()
check("API verificar-email inexistente retorna vazio", data["existe"] is False)

# ====================================================================
# TESTES: Login com email duplicado
# ====================================================================
print("\n--- 11. TESTE: Login com email duplicado ---")

r = client.post("/login", data={"email": "familia@email.com", "senha": "123456"})
check("Login familia@email.com", r.status_code in (200, 302))

familia_count = db.fetch_all("SELECT id, nome, tipo FROM usuarios WHERE email = 'familia@email.com'")
check("Login email duplicado: 2 contas existem", len(familia_count) == 2)
for u in familia_count:
    print(f"      ID={u['id']}, nome={u['nome']}, tipo={u['tipo']}")

# ====================================================================
# TESTES: Admin do estabelecimento
# ====================================================================
print("\n--- 12. TESTE: Acesso do Admin do estabelecimento ---")

check("Admin Odonto ja criado", admin_odonto is not None)

r = client.post("/login", data={"email": "admin_odonto@email.com", "senha": "123456"})
check("Login admin Clinica Odonto", r.status_code in (200, 302))

# Admin: resolver_estabelecimento auto-seleciona primeiro estab (se nao tem cookie)
r = client.get("/prontuarios")
html = r.text
pront_ids_html = parse_prontuario_ids(html)

check("Admin Odonto ve prontuario Maria", 1 in pront_ids_html)
check("Admin Odonto ve prontuario Pedro", 2 in pront_ids_html)
check("Admin Odonto ve prontuario Pai Ferreira", 4 in pront_ids_html)
check("Admin Odonto ve prontuario Filho Ferreira", 5 in pront_ids_html)
check("Admin Odonto NAO ve prontuario Joao", 3 not in pront_ids_html,
      "Joao esta em Hospital Saude")
check("Admin Odonto NAO ve prontuario Ana Costa (Hospital)", 6 not in pront_ids_html,
      "Ana Costa esta em Hospital Saude")

# ====================================================================
# TESTES: Super admin ve todos os prontuarios
# ====================================================================
print("\n--- 13. TESTE: Super admin ve prontuarios ---")

r = client.post("/login", data={"email": "marcusodontocotta@gmail.com", "senha": "admin123"})
check("Login super admin", r.status_code in (200, 302))

# Super admin com cookie estab1 ve prontuarios do estab1
client.cookies.set("estabelecimento_id", str(estab1_id))
r = client.get("/prontuarios")
html = r.text
pront_ids_html = parse_prontuario_ids(html)

check("Super admin (estab1) ve prontuario Maria", 1 in pront_ids_html)
check("Super admin (estab1) ve prontuario Pedro", 2 in pront_ids_html)
check("Super admin (estab1) ve prontuario Pai Ferreira", 4 in pront_ids_html)
check("Super admin (estab1) NAO ve prontuario Joao (Hospital)", 3 not in pront_ids_html)

# Super admin com cookie estab2 ve prontuarios do estab2
client.cookies.set("estabelecimento_id", str(estab2_id))
r = client.get("/prontuarios")
html = r.text
pront_ids_html = parse_prontuario_ids(html)

check("Super admin (estab2) ve prontuario Joao Oliveira", 3 in pront_ids_html)
check("Super admin (estab2) ve prontuario Ana Costa", 6 in pront_ids_html)
check("Super admin (estab2) NAO ve prontuario Maria (Odonto)", 1 not in pront_ids_html)

# Super admin pode acessar QUALQUER prontuario individualmente
if pront_ids.get("Maria Silva"):
    r = client.get(f"/prontuarios/{pront_ids['Maria Silva']}")
    check("Super admin acessa prontuario Maria (estab1) mesmo com estab2 cookie",
          r.status_code == 200)

if pront_ids.get("Joao Oliveira"):
    r = client.get(f"/prontuarios/{pront_ids['Joao Oliveira']}")
    check("Super admin acessa prontuario Joao (estab2) mesmo com estab1 cookie",
          r.status_code == 200)

# ====================================================================
# TESTES: Recepcionista
# ====================================================================
print("\n--- 14. TESTE: Acesso do recepcionista Joao ---")

# Limpar cookies anteriores
for c in list(client.cookies.jar):
    client.cookies.delete(c.name)
r = client.post("/login", data={"email": "joao_recep@email.com", "senha": "123456"})
check("Login Joao Recep", r.status_code in (200, 302))
estab_cookie = client.cookies.get("estabelecimento_id")
print(f"    Cookie recep: {estab_cookie}")

r = client.get("/prontuarios")
html = r.text
pront_ids_html = parse_prontuario_ids(html)
print(f"    Prontuarios visiveis IDs: {pront_ids_html}")

check("Recep Joao ve prontuario Maria", 1 in pront_ids_html)
check("Recep Joao ve prontuario Pedro", 2 in pront_ids_html)
check("Recep Joao NAO ve prontuario Joao", 3 not in pront_ids_html,
      "Joao esta em Hospital Saude")

# ====================================================================
# TESTES: Cross-estab individual
# ====================================================================
print("\n--- 15. TESTE: ver_prontuario cross-estab via API ---")

r = client.post("/login", data={"email": "dra_ana@email.com", "senha": "123456"})
check("Login Dra. Ana (cross-estab)", r.status_code in (200, 302))

if pront_ids.get("Ana Costa"):
    r = client.get(f"/prontuarios/{pront_ids['Ana Costa']}")
    check("Dra. Ana BLOQUEADA de prontuario Ana Costa (Hospital Saude)",
          r.status_code == 403, f"status={r.status_code}")

if pront_ids.get("Ana Costa Dupla"):
    r = client.get(f"/prontuarios/{pront_ids['Ana Costa Dupla']}")
    check("Dra. Ana acessa prontuario Ana Costa Dupla (Clinica Odonto)",
          r.status_code == 200, f"status={r.status_code}")

# ====================================================================
# RESUMO
# ====================================================================
print("\n" + "=" * 70)
total = ok_count + len(errors)
print(f"RESULTADO: {ok_count}/{total} passaram, {len(errors)} falharam")
if errors:
    print("\nFALHAS:")
    for e in errors:
        print(f"  - {e}")
print("=" * 70)

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
from utils.auth import hash_senha
pwd_hash = hash_senha("pac123")
db.execute("INSERT INTO usuarios (id, nome, email, senha_hash, tipo, ativo) VALUES (2, 'PacienteIDOR', 'paciente@test.com', %s, 'paciente', TRUE) ON DUPLICATE KEY UPDATE ativo=TRUE", (pwd_hash,))
db.execute("INSERT INTO usuarios (id, nome, email, senha_hash, tipo, ativo) VALUES (3, 'PacienteIDOR2', 'paciente2@test.com', %s, 'paciente', TRUE) ON DUPLICATE KEY UPDATE ativo=TRUE", (pwd_hash,))
db.execute("ALTER TABLE usuarios AUTO_INCREMENT = 4")
db.execute("INSERT IGNORE INTO profissional_estabelecimento (usuario_id, estabelecimento_id) VALUES (1, 1)")
db.execute("INSERT IGNORE INTO paciente_estabelecimento (usuario_id, estabelecimento_id) VALUES (2, 1), (3, 1)")
db.execute("SET FOREIGN_KEY_CHECKS = 1")
db.close()
print("restore_db: estado restaurado")
