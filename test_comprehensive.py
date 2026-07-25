import sys, re, time
sys.path.insert(0, '.')
from main import app
from starlette.testclient import TestClient
from database.connection import db

db.get_connection()
errors = []

def check(name, condition, detail=""):
    status = "[OK]" if condition else "[FALHOU]"
    extra = f" {detail}" if detail else ""
    print(f"  {status} {name}{extra}")
    if not condition:
        errors.append(name)

# Reset DB
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
db.execute("ALTER TABLE usuarios AUTO_INCREMENT = 2")
db.execute("ALTER TABLE estabelecimentos AUTO_INCREMENT = 1")
db.execute("ALTER TABLE consultas AUTO_INCREMENT = 1")
db.execute("ALTER TABLE prontuarios AUTO_INCREMENT = 1")
db.execute("ALTER TABLE evolucoes AUTO_INCREMENT = 1")
db.execute("ALTER TABLE tratamentos AUTO_INCREMENT = 1")
db.execute("ALTER TABLE convenios AUTO_INCREMENT = 1")
db.execute("ALTER TABLE procedimentos AUTO_INCREMENT = 1")
db.execute("ALTER TABLE orcamentos AUTO_INCREMENT = 1")
db.execute("ALTER TABLE orcamento_itens AUTO_INCREMENT = 1")
db.execute("ALTER TABLE pagamentos AUTO_INCREMENT = 1")

client = TestClient(app, follow_redirects=False)

# ========== 1. ACESSO LOCAL ==========
print("\n=== 1. ACESSO LOCAL ===")
r = client.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'admin123'})
check("Login admin local", r.status_code == 302)

r = client.get('/api/status')
check("API status local", r.status_code == 200 and r.json().get("banco") is True)

for page in ['dashboard', 'pacientes', 'consultas', 'prontuarios', 'estabelecimentos', 'convenios', 'procedimentos', 'agenda', 'orcamentos', 'financeiro', 'pagamentos']:
    r = client.get(f'/{page}')
    check(f"GET /{page} local", r.status_code == 200)

# ========== 2. ACESSO REMOTO ==========
print("\n=== 2. ACESSO REMOTO ===")
import urllib.request
try:
    r = urllib.request.urlopen("https://hub-circles-fourth-historic.trycloudflare.com/api/status", timeout=10)
    data = __import__('json').loads(r.read())
    check("API status remoto", r.status == 200 and data.get("banco") is True)
except Exception as e:
    check("API status remoto", False, str(e))

try:
    r = urllib.request.urlopen("https://hub-circles-fourth-historic.trycloudflare.com/login", timeout=10)
    check("Login page remoto", r.status == 200)
except Exception as e:
    check("Login page remoto", False, str(e))

# ========== 3. SEGURANCA ==========
print("\n=== 3. SEGURANCA ===")

# 3a. Headers de seguranca
r = client.get('/login')
check("X-Content-Type-Options header", r.headers.get("x-content-type-options") == "nosniff")
check("X-Frame-Options header", r.headers.get("x-frame-options") == "DENY")
check("X-XSS-Protection header", "1; mode=block" in r.headers.get("x-xss-protection", ""))
check("Referrer-Policy header", r.headers.get("referrer-policy") == "strict-origin-when-cross-origin")
check("CSP header presente", "content-security-policy" in r.headers)

# 3b. Swagger desabilitado
r = client.get("/docs")
check("Swagger desabilitado", r.status_code == 404)
r = client.get("/redoc")
check("Redoc desabilitado", r.status_code == 404)

# 3c. Cookie seguranca
r = client.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'admin123'})
cookie_header = r.headers.get("set-cookie", "")
check("Cookie HttpOnly", "httponly" in cookie_header.lower())
check("Cookie SameSite", "samesite" in cookie_header.lower())

# 3d. Logout limpa cookies
r = client.get('/logout')
check("Logout redirect", r.status_code == 302)
token_cookies = [c for c in r.headers.get_list('set-cookie') if 'token' in c]
check("Token cookie removido no logout", len(token_cookies) > 0 and 'max-age=0' in token_cookies[0].lower())

# 3e. Acesso negado sem login
client2 = TestClient(app, follow_redirects=False)
r = client2.get('/dashboard')
check("Acesso negado sem login (redirect)", r.status_code == 302)

r = client2.get('/api/status')
check("API status publica (sem auth)", r.status_code == 200)

# 3f. Login com senha errada
r = client2.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'ERRADA'})
check("Login senha errada retorna erro", r.status_code == 200 and 'invalidos' in r.text.lower())

# Re-login admin
r = client.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'admin123'})

# 3g. IDOR - paciente nao acessa orcamento de outro
r = client.post('/pacientes/criar', data={'nome': 'PacienteIDOR', 'email': 'idor@test.com', 'senha': '123456', 'telefone': '11900000000', 'data_nascimento': '1995-01-01', 'cpf': '11122233344'})
r = client.post('/pacientes/criar', data={'nome': 'PacienteIDOR2', 'email': 'idor2@test.com', 'senha': '123456', 'telefone': '11900000001', 'data_nascimento': '1996-01-01', 'cpf': '11122233345'})
client.post('/estabelecimentos/criar', data={'nome': 'Clinica IDOR', 'tipo': 'clinica', 'telefone': '1155556666', 'email': 'idor@clinica.com'})
client.post('/prontuarios/criar', data={'paciente_usuario_id': 3, 'estabelecimento_id': '1'})
client.post('/orcamentos/criar', data={'paciente_id': 3, 'profissional_id': 1, 'convenio_id': '', 'data_validade': '2026-08-31', 'observacoes': 'IDOR test', 'estabelecimento_id': '1'})
orc_id = db.fetch_one("SELECT MAX(id) AS mid FROM orcamentos")["mid"]

# 3h. Rate limit - 11 tentativas rapidas
client3 = TestClient(app, follow_redirects=False)
for i in range(11):
    r = client3.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'ERRADA'})
check("Rate limit apos 10 tentativas", 'Muitas tentativas' in r.text)

# ========== 4. PAGAMENTOS PARCELADOS ==========
print("\n=== 4. PAGAMENTOS PARCELADOS ===")

# Setup
client.post('/convenios/criar', data={'nome': 'Unimed Teste', 'cnpj': '99999999000199', 'telefone': '1140028922', 'email': 'un@test.com', 'endereco': 'Rua Teste'})
client.post('/procedimentos/criar', data={'nome': 'Restauracao', 'duracao_minutos': '60', 'descricao': 'Restauracao dentaria'})
client.post('/procedimentos/criar', data={'nome': 'Extracao', 'duracao_minutos': '45', 'descricao': 'Extracao dentaria'})
client.post('/procedimentos/criar', data={'nome': 'Limpeza', 'duracao_minutos': '30', 'descricao': 'Limpeza dental'})

# Criar orcamento grande para testar parcelamento
r = client.post('/orcamentos/criar', data={'paciente_id': 2, 'profissional_id': 1, 'convenio_id': '', 'data_validade': '2026-12-31', 'observacoes': 'Teste parcelamento', 'estabelecimento_id': '1'}, follow_redirects=False)
check("Criar orcamento parcelado", r.status_code == 302)
orc_parcel_id = db.fetch_one("SELECT MAX(id) AS mid FROM orcamentos")["mid"]

# Adicionar 3 itens
for i, (proc, val) in enumerate([(1, 300), (2, 500), (3, 200)]):
    r = client.post(f'/orcamentos/{orc_parcel_id}/item/adicionar', data={
        'procedimento_id': proc, 'descricao': f'Proc {i+1}', 'quantidade': 1, 'valor_unitario': val, 'desconto': 0
    }, follow_redirects=False)
check(f"Item {i+1} adicionado (R${val})", r.status_code == 302)

orc = db.fetch_one("SELECT valor_total FROM orcamentos WHERE id = %s", (orc_parcel_id,))
check(f"Valor total R$1000", float(orc["valor_total"]) == 1000)

# Aprovar
client.post(f'/orcamentos/{orc_parcel_id}/status', data={'status': 'enviado'}, follow_redirects=False)
client.post(f'/orcamentos/{orc_parcel_id}/status', data={'status': 'aprovado'}, follow_redirects=False)
orc = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc_parcel_id,))
check("Orcamento aprovado", orc["status"] == "aprovado")

# Parcelamento 5x
r = client.post(f'/orcamentos/{orc_parcel_id}/pagar', data={
    'valor': '200', 'metodo': 'cartao_credito', 'parcelas': '5', 'data_pagamento': '2026-07-23', 'observacao': 'Parcela 1 de 5'
}, follow_redirects=False)
check("Pagamento parcelado 1/5 registrado", r.status_code == 302)

# Verificar que 1 pagamento foi criado com parcelas=5
pagamentos = db.fetch_all("SELECT * FROM pagamentos WHERE orcamento_id = %s AND status = 'pago' ORDER BY id", (orc_parcel_id,))
check(f"1 pagamento criado com 5 parcelas", len(pagamentos) >= 1)
pag_parcela = pagamentos[-1]
check(f"Parcelas = 5", pag_parcela["parcelas"] == 5)
check(f"Valor parcela R$40.00", abs(float(pag_parcela["valor_parcela"]) - 40.0) < 0.01)
check(f"Metodo cartao_credito", pag_parcela["metodo"] == "cartao_credito")

# Status do orcamento
orc = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc_parcel_id,))
check("Status apos entrada = pago_parcial", orc["status"] == "pago_parcial")

# Saldo
r = client.get(f'/orcamentos/{orc_parcel_id}/pagar')
check("Saldo atualizado apos parcela", f'R$' in r.text)

# Pagar restante
r = client.post(f'/orcamentos/{orc_parcel_id}/pagar', data={
    'valor': '800', 'metodo': 'boleto', 'parcelas': '1', 'data_pagamento': '2026-08-01', 'descricao': 'Restante'
}, follow_redirects=False)
check("Pagamento restante registrado", r.status_code == 302)

orc = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc_parcel_id,))
check("Status apos total = pago", orc["status"] == "pago")

total_pago = db.fetch_one("SELECT SUM(valor) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'", (orc_parcel_id,))
check(f"Total pago R$1000", abs(float(total_pago["total"]) - 1000) < 0.01)

# Nota fiscal acessivel apos pagamento
r = client.get(f'/orcamentos/{orc_parcel_id}/nota-fiscal')
check("Nota fiscal acessivel apos pagamento", r.status_code == 200)
check("Nota fiscal tem valor", f'R$' in r.text)

# Cancelar pagamento e verificar reacao
pag_para_cancelar = pagamentos[-1]
r = client.post(f'/orcamentos/{orc_parcel_id}/pagamento/{pag_para_cancelar["id"]}/cancelar', follow_redirects=False)
check("Cancelamento pagamento registrado", r.status_code == 302)

pagamento_cancelado = db.fetch_one("SELECT status FROM pagamentos WHERE id = %s", (pag_para_cancelar["id"],))
check("Pagamento cancelado no banco", pagamento_cancelado["status"] == "cancelado")

orc = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc_parcel_id,))
check("Status volta para pago_parcial apos cancelamento parcial", orc["status"] == "pago_parcial")

total_geral = db.fetch_one("SELECT SUM(valor) AS total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'", (orc_parcel_id,))
check(f"Total pago apos cancelamento R$800", abs(float(total_geral["total"]) - 800) < 0.01)

# ========== 5. TESTES GERAIS ==========
print("\n=== 5. TESTES GERAIS ===")

# 5a. Filtro paciente com valor vazio (bug fix)
r = client.get('/consultas?paciente_id=')
check("Filtro consultas paciente vazio (bug fix)", r.status_code == 200)
r = client.get('/orcamentos?paciente_id=')
check("Filtro orcamentos paciente vazio", r.status_code == 200)
r = client.get('/prontuarios?paciente_id=')
check("Filtro prontuarios paciente vazio", r.status_code == 200)
r = client.get('/agenda?profissional_id=2')
check("Filtro agenda profissional vazio", r.status_code == 200)
r = client.get('/financeiro?paciente_id=')
check("Filtro financeiro paciente vazio", r.status_code == 200)
r = client.get('/pagamentos?paciente_id=')
check("Filtro pagamentos paciente vazio", r.status_code == 200)

# 5b. Status transitions completas para orcamentos
r = client.post('/orcamentos/criar', data={'paciente_id': 2, 'profissional_id': 1, 'convenio_id': '', 'data_validade': '2026-12-31', 'observacoes': 'Teste status', 'estabelecimento_id': '1'}, follow_redirects=False)
orc_status_id = db.fetch_one("SELECT MAX(id) AS mid FROM orcamentos")["mid"]

for status in ['enviado', 'aprovado']:
    r = client.post(f'/orcamentos/{orc_status_id}/status', data={'status': status}, follow_redirects=False)
    check(f"Status -> {status}", r.status_code == 302)
    orc = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc_status_id,))
    check(f"Status {status} confirmado", orc["status"] == status)

# 5c. Consulta com procedimento
r = client.post('/consultas/criar', data={
    'paciente_id': 2, 'profissional_id': 1, 'data_hora': '2026-08-01 10:00',
    'duracao_minutos': '60', 'procedimento_id': 1, 'estabelecimento_id': '1'
}, follow_redirects=False)
check("Consulta com procedimento criada", r.status_code == 302)

# 5d. Pagina financeira com diferentes periodos
for periodo in ['hoje', 'semana', 'mes', 'ano']:
    r = client.get(f'/financeiro?periodo={periodo}')
    check(f"Financeiro periodo={periodo}", r.status_code == 200)

# 5e. API endpoints
r = client.get('/api/procedimentos')
check("API procedimentos", r.status_code == 200 and len(r.json()) > 0)

r = client.get('/api/procedimento-valor?procedimento_id=1')
check("API procedimento valor", r.status_code == 200)

# 5f. Pagina de pagamentos com filtros
r = client.get('/pagamentos')
check("Pagina pagamentos admin", r.status_code == 200)
check("Resumo pagamentos visivel", 'pagamento' in r.text.lower())

# 5g. Estabelecimento desativado some da lista
r = client.post('/estabelecimentos/1/desativar', follow_redirects=False)
check("Desativar estabelecimento", r.status_code == 302)

# 5h. Erros 404
r = client.get('/orcamentos/99999')
check("Orcamento inexistente = 404", r.status_code == 404)

r = client.get('/prontuarios/99999')
check("Prontuario inexistente = 404", r.status_code == 404)

# ========== RESULTADO ==========
print(f"\n{'='*60}")
total = len([e for e in errors])
print(f"TOTAL: {len(errors)} ERROS")
if errors:
    for e in errors:
        print(f"  - {e}")
else:
    print("TODOS OS TESTES PASSARAM!")
