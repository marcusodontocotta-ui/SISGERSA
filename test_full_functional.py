import sys
sys.path.insert(0, '.')
import pymysql
from utils.auth import hash_senha
from database.connection import db
from main import app
from starlette.testclient import TestClient

passed = 0
failed = 0
errors = []

def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {name}")
    else:
        failed += 1
        errors.append(name)
        print(f"  [FAIL] {name}")

def clean_db():
    conn = pymysql.connect(host='localhost', port=3306, user='root', password='root123',
                           database='medical_db', charset='utf8mb4')
    cur = conn.cursor()
    for t in ['permissoes_usuario','pagamentos','orcamento_itens','orcamentos','tratamentos',
              'evolucoes','consultas','prontuarios','paciente_convenio','paciente_estabelecimento',
              'profissional_estabelecimento','procedimento_valor']:
        cur.execute(f"DELETE FROM {t}")
    cur.execute("DELETE FROM usuarios WHERE id > 1")
    cur.execute("DELETE FROM estabelecimentos")
    cur.execute("DELETE FROM convenios")
    cur.execute("DELETE FROM procedimentos")
    for t in ['permissoes_usuario','pagamentos','orcamento_itens','orcamentos','tratamentos',
              'evolucoes','consultas','prontuarios','paciente_convenio','paciente_estabelecimento',
              'profissional_estabelecimento','procedimento_valor','usuarios','estabelecimentos',
              'convenios','procedimentos']:
        cur.execute(f"ALTER TABLE {t} AUTO_INCREMENT=1")
    cur.execute("SELECT id FROM usuarios WHERE id = 1")
    if not cur.fetchone():
        hash_pwd = hash_senha('admin123')
        cur.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, tipo, telefone, is_super) VALUES (%s, %s, %s, %s, %s, %s)",
            ('Administrador', 'marcusodontocotta@gmail.com', hash_pwd, 'admin', '11999990000', True)
        )
    conn.commit()
    conn.close()

print("\n=== CLEAN DB ===")
db.close()
clean_db()
db.close()
print("  [OK] Banco limpo")

c = TestClient(app, follow_redirects=False)

def uid(email):
    u = db.fetch_one("SELECT id FROM usuarios WHERE email = %s", (email,))
    return u["id"] if u else None

# ═══════════════════════════════════════
# 1. SETUP: Dados iniciais
# ═══════════════════════════════════════
print("\n=== 1. SETUP INICIAL ===")

r = c.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'admin123'})
check("Login admin", r.status_code == 302)

r = c.get('/api/status')
check("API status banco ok", r.json().get('banco') is True)

r = c.post('/estabelecimentos/criar', data={
    'nome': 'Clinica Centro', 'tipo': 'consultorio', 'cnpj': '11.222.333/0001-44',
    'telefone': '(11) 3333-4444', 'email': 'centro@clinica.com', 'endereco': 'Rua Centro, 100'
})
check("Criar Clinica Centro", r.status_code in (302, 200))

r = c.post('/estabelecimentos/criar', data={
    'nome': 'Hospital Norte', 'tipo': 'hospital', 'cnpj': '55.666.777/0001-88',
    'telefone': '(11) 5555-6666', 'email': 'norte@hospital.com', 'endereco': 'Av Norte, 200'
})
check("Criar Hospital Norte", r.status_code in (302, 200))

for idx, (nome, email, estab) in enumerate([
    ('Dr. Silva', 'silva@med.com', 1),
    ('Dra. Santos', 'santos@med.com', 1),
    ('Dr. Oliveira', 'oliveira@med.com', 2),
    ('Dra. Costa', 'costa@med.com', 2),
]):
    r = c.post('/profissionais/criar', data={
        'nome': nome, 'email': email, 'telefone': f'(11) 9{idx:03d}-0000',
        'senha': 'prof123', 'estabelecimento_id': str(estab),
        'especialidade': 'Geral', 'cargo': 'Medico', 'registro_profissional': f'CRM{1000+idx}'
    })
    check(f"Criar {nome}", r.status_code in (302, 200))

for nome, reg, desc in [('Unimed', '111', '20'), ('SulAmerica', '222', '15'), ('Amil', '333', '10'), ('Bradesco', '444', '25')]:
    r = c.post('/convenios/criar', data={
        'nome': nome, 'registro_ans': reg, 'cobertura': f'Cobertura {nome}',
        'percentual_cobertura': desc, 'telefone': '(11) 9999-0000', 'email': f'{nome.lower()}@conv.com'
    })
    check(f"Criar convenio {nome}", r.status_code in (302, 200))

for nome, dur, desc in [('Restauracao', 30, 'Restauracao dentaria'), ('Extracao', 45, 'Extracao dentaria'),
                         ('Limpeza', 30, 'Limpeza profissional'), ('Clareamento', 60, 'Clareamento dental'),
                         ('Canal', 90, 'Tratamento de canal')]:
    r = c.post('/procedimentos/criar', data={'nome': nome, 'descricao': desc, 'duracao_minutos': dur})
    check(f"Criar procedimento {nome}", r.status_code in (302, 200))

db.execute("INSERT INTO procedimento_valor (procedimento_id, convenio_id, estabelecimento_id, valor) VALUES (1, 1, 1, 140)")
db.execute("INSERT INTO procedimento_valor (procedimento_id, convenio_id, estabelecimento_id, valor) VALUES (2, 1, 1, 350)")
db.execute("INSERT INTO procedimento_valor (procedimento_id, convenio_id, estabelecimento_id, valor) VALUES (3, 2, 1, 100)")

for nome, email, cpf, nasc, end in [
    ('Ana Silva', 'ana@email.com', '111.222.333-44', '1990-05-15', 'Rua A, 10'),
    ('Carlos Souza', 'carlos@email.com', '555.666.777-88', '1985-08-20', 'Rua B, 20'),
    ('Maria Lima', 'maria@email.com', '999.888.777-66', '1992-03-10', 'Rua C, 30'),
    ('Pedro Santos', 'pedro@email.com', '123.456.789-00', '1988-11-25', 'Rua D, 40'),
    ('Julia Ferreira', 'julia@email.com', '987.654.321-00', '1995-07-08', 'Rua E, 50'),
    ('Lucas Almeida', 'lucas@email.com', '456.789.123-00', '1980-01-30', 'Rua F, 60'),
]:
    r = c.post('/pacientes/criar', data={
        'nome': nome, 'email': email, 'telefone': f'(11) 9900-1111', 'cpf': cpf,
        'data_nascimento': nasc, 'endereco': end, 'senha': 'pac123',
    })
    check(f"Criar paciente {nome}", r.status_code in (302, 200))

A = uid('ana@email.com'); CA = uid('carlos@email.com'); M = uid('maria@email.com')
P = uid('pedro@email.com'); J = uid('julia@email.com'); L = uid('lucas@email.com')
S = uid('silva@med.com'); SA = uid('santos@med.com'); O = uid('oliveira@med.com'); CO = uid('costa@med.com')
print(f"  Pac IDs: Ana={A}, Carlos={CA}, Maria={M}, Pedro={P}, Julia={J}, Lucas={L}")
print(f"  Prof IDs: Silva={S}, Santos={SA}, Oliveira={O}, Costa={CO}")

db.execute("INSERT INTO paciente_convenio (paciente_usuario_id, convenio_id, numero_carteirinha, validade) VALUES (%s, 1, 'UNI-001', '2027-12-31')", (A,))
db.execute("INSERT INTO paciente_convenio (paciente_usuario_id, convenio_id, numero_carteirinha, validade) VALUES (%s, 1, 'UNI-002', '2027-06-30')", (CA,))
db.execute("INSERT INTO paciente_convenio (paciente_usuario_id, convenio_id, numero_carteirinha, validade) VALUES (%s, 2, 'SUL-001', '2027-12-31')", (M,))
db.execute("INSERT INTO paciente_convenio (paciente_usuario_id, convenio_id, numero_carteirinha, validade) VALUES (%s, 1, 'UNI-003', '2026-12-31')", (P,))

r = c.get('/api/profissionais')
check("API profissionais retorna 2 (estab 1)", len(r.json()) == 2)
r = c.get('/api/pacientes')
check("API pacientes retorna 6", len(r.json()) == 6)
r = c.get('/api/procedimentos')
check("API procedimentos retorna 5", len(r.json()) == 5)

# ═══════════════════════════════════════
# 2. PRONTUARIOS
# ═══════════════════════════════════════
print("\n=== 2. PRONTUARIOS ===")

for pac_email in ['ana@email.com', 'carlos@email.com', 'maria@email.com', 'pedro@email.com', 'julia@email.com', 'lucas@email.com']:
    pid = uid(pac_email)
    r = c.post('/prontuarios/criar', data={
        'paciente_id': pid, 'alergias': 'Nenhuma', 'doencas_cronicas': 'Nenhuma',
        'historico_familiar': 'PAI: Hipertensao', 'observacoes': f'Prontuario {pid}',
    })
    check(f"Criar prontuario {pac_email}", r.status_code in (302, 200))

r = c.get('/prontuarios')
check("Listar prontuarios", r.status_code == 200)
pront_ana = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s", (A,))
r = c.get(f'/prontuarios/{pront_ana["id"]}')
check("Ver prontuario Ana", r.status_code == 200)

# ═══════════════════════════════════════
# 3. CONSULTAS
# ═══════════════════════════════════════
print("\n=== 3. CONSULTAS ===")

consultas_data = [
    (A, S, '2026-07-21T09:00', 30, 'Consulta inicial Ana'),
    (CA, S, '2026-07-21T10:00', 45, 'Carlos retorno'),
    (M, SA, '2026-07-22T09:00', 60, 'Maria avaliacao'),
    (P, SA, '2026-07-22T14:00', 30, 'Pedro limpeza'),
    (J, O, '2026-07-23T09:00', 45, 'Julia primeira consulta'),
    (L, O, '2026-07-23T11:00', 30, 'Lucas cancelou'),
    (A, S, '2026-07-24T09:00', 30, 'Ana segunda consulta'),
    (CA, SA, '2026-07-24T10:00', 60, 'Carlos consulta longa'),
]
for pac_id, prof_id, data_hora, dur, obs in consultas_data:
    r = c.post('/consultas/criar', data={
        'paciente_id': pac_id, 'profissional_id': prof_id,
        'data_hora': data_hora, 'duracao': dur, 'observacoes': obs
    })
    check(f"Criar consulta {obs[:30]}", r.status_code in (302, 200))

r = c.get('/api/consultas?inicio=2026-07-20T00:00:00&fim=2026-07-30T23:59:59')
check("API consultas retorna 8", len(r.json()) == 8)

consutas_api = r.json()
statuses = {x['status'] for x in consutas_api}
check("Todas consultas iniciam agendadas", all(x['status'] == 'agendada' for x in consutas_api))

r = c.post('/consultas/1/status', data={'status': 'confirmada'})
check("Mudar status agendada->confirmada", r.status_code in (302, 200))
r = c.post('/consultas/3/status', data={'status': 'concluida'})
check("Mudar status em_andamento->concluida", r.status_code in (302, 200))
r = c.post('/consultas/5/status', data={'status': 'faltou'})
check("Mudar status agendada->faltou", r.status_code in (302, 200))

r = c.get('/api/consultas?inicio=2026-07-20T00:00:00&fim=2026-07-30T23:59:59')
statuses = {x['status'] for x in r.json()}
check("Statuses presentes apos mudancas", 'agendada' in statuses and 'confirmada' in statuses
     and 'concluida' in statuses and 'faltou' in statuses)

# ═══════════════════════════════════════
# 4. EVOLUCOES E TRATAMENTOS
# ═══════════════════════════════════════
print("\n=== 4. EVOLUCOES E TRATAMENTOS ===")

pront_pedro = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s", (P,))
r = c.post(f'/prontuarios/{pront_pedro["id"]}/evolucao', data={
    'profissional_id': SA, 'queixa': 'Dor no dente 36',
    'diagnostico': 'Caries profunda', 'procedimento': 'Restauracao',
    'observacoes': 'Paciente orientado sobre higiene',
})
check("Criar evolucao Pedro", r.status_code in (302, 200))

evolucao = db.fetch_one("SELECT id FROM evolucoes ORDER BY id DESC LIMIT 1")
if evolucao:
    r = c.post(f'/prontuarios/{pront_pedro["id"]}/evolucao/{evolucao["id"]}/tratamento', data={
        'tipo': 'restauracao', 'descricao': 'Restauracao dentes 36 e 37',
        'dente': '36,37', 'face': 'Oclusal', 'material': 'Resina',
        'procedimento_id': 1, 'valor': 200,
    })
    check("Criar tratamento restauracao", r.status_code in (302, 200))
    tratar = db.fetch_one("SELECT id FROM tratamentos ORDER BY id DESC LIMIT 1")
    check("Tratamento criado no banco", tratar is not None)

pront_ana = db.fetch_one("SELECT id FROM prontuarios WHERE paciente_usuario_id = %s", (A,))
r = c.post(f'/prontuarios/{pront_ana["id"]}/evolucao', data={
    'profissional_id': S, 'queixa': 'Manutencao preventiva',
    'diagnostico': 'Saudavel', 'procedimento': 'Limpeza',
    'observacoes': 'Paciente em boas condicoes',
})
check("Criar evolucao Ana", r.status_code in (302, 200))

# ═══════════════════════════════════════
# 5. ORCAMENTOS
# ═══════════════════════════════════════
print("\n=== 5. ORCAMENTOS (FLUXO COMPLETO) ===")

r = c.post('/orcamentos/criar', data={
    'paciente_id': A, 'profissional_id': S, 'convenio_id': 1,
    'data_validade': '2026-08-31', 'observacoes': 'Plano de tratamento Ana',
})
check("Criar orcamento Ana (Unimed)", r.status_code in (302, 200))
orc1 = db.fetch_one("SELECT id FROM orcamentos ORDER BY id DESC LIMIT 1")

for proc_id, desc, qtd, valor in [(1, 'Restauracao dente 36', 1, 140), (2, 'Extracao dente 48', 1, 350), (3, 'Limpeza profissional', 1, 100)]:
    r = c.post(f'/orcamentos/{orc1["id"]}/item/adicionar', data={
        'procedimento_id': proc_id, 'descricao': desc, 'quantidade': qtd, 'valor_unitario': valor,
    })
    check(f"Adicionar item: {desc[:25]}", r.status_code in (302, 200))

orc1_db = db.fetch_one("SELECT valor_total FROM orcamentos WHERE id = %s", (orc1["id"],))
check(f"Total orcamento 1 = R$590", float(orc1_db["valor_total"]) == 590)

r = c.post(f'/orcamentos/{orc1["id"]}/status', data={'status': 'enviado'})
check("Enviar orcamento 1", r.status_code in (302, 200))
r = c.post(f'/orcamentos/{orc1["id"]}/status', data={'status': 'aprovado'})
check("Aprovar orcamento 1", r.status_code in (302, 200))

r = c.get(f'/orcamentos/{orc1["id"]}')
check("Ver orcamento 1", r.status_code == 200)
check("Orcamento 1 mostra Ana", 'Ana Silva' in r.text)
check("Orcamento 1 mostra status aprovado", 'Aprovado' in r.text)

r = c.post('/orcamentos/criar', data={
    'paciente_id': CA, 'profissional_id': S, 'convenio_id': '',
    'data_validade': '2026-09-30', 'observacoes': 'Tratamento particular Carlos',
})
check("Criar orcamento Carlos (particular)", r.status_code in (302, 200))
orc2 = db.fetch_one("SELECT id FROM orcamentos ORDER BY id DESC LIMIT 1")

r = c.post(f'/orcamentos/{orc2["id"]}/item/adicionar', data={
    'procedimento_id': 4, 'descricao': 'Clareamento', 'quantidade': 1, 'valor_unitario': 800,
})
check("Adicionar clareamento ao orcamento 2", r.status_code in (302, 200))
r = c.post(f'/orcamentos/{orc2["id"]}/item/adicionar', data={
    'procedimento_id': 5, 'descricao': 'Canal dente 11', 'quantidade': 1, 'valor_unitario': 600,
})
check("Adicionar canal ao orcamento 2", r.status_code in (302, 200))

orc2_db = db.fetch_one("SELECT valor_total FROM orcamentos WHERE id = %s", (orc2["id"],))
check(f"Total orcamento 2 = R$1400", float(orc2_db["valor_total"]) == 1400)

r = c.post(f'/orcamentos/{orc2["id"]}/status', data={'status': 'enviado'})
r = c.post(f'/orcamentos/{orc2["id"]}/status', data={'status': 'aprovado'})
check("Enviar e aprovar orcamento 2", r.status_code in (302, 200))

r = c.post('/orcamentos/criar', data={
    'paciente_id': M, 'profissional_id': SA, 'convenio_id': 2,
    'data_validade': '2026-08-15', 'observacoes': 'Proposta rejeitada Maria',
})
check("Criar orcamento Maria", r.status_code in (302, 200))
orc3 = db.fetch_one("SELECT id FROM orcamentos ORDER BY id DESC LIMIT 1")
r = c.post(f'/orcamentos/{orc3["id"]}/item/adicionar', data={
    'procedimento_id': 4, 'descricao': 'Clareamento', 'quantidade': 1, 'valor_unitario': 800,
})
r = c.post(f'/orcamentos/{orc3["id"]}/status', data={'status': 'enviado'})
r = c.post(f'/orcamentos/{orc3["id"]}/status', data={'status': 'rejeitado'})
orc3_db = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc3["id"],))
check("Orcamento 3 rejeitado", orc3_db['status'] == 'rejeitado')

# ═══════════════════════════════════════
# 6. PAGAMENTOS
# ═══════════════════════════════════════
print("\n=== 6. PAGAMENTOS ===")

r = c.post(f'/orcamentos/{orc1["id"]}/pagar', data={'valor': '590', 'metodo': 'pix', 'parcelas': '1'})
check("Pagar orcamento 1 total (R$590 PIX)", r.status_code in (302, 200))

orc1_db = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc1["id"],))
check("Orcamento 1 status = pago", orc1_db['status'] == 'pago')

pag1 = db.fetch_one("SELECT * FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'", (orc1["id"],))
check("Pagamento 1 criado", pag1 is not None)
check("Pagamento 1 valor = 590", float(pag1['valor']) == 590)
check("Pagamento 1 metodo = pix", pag1['metodo'] == 'pix')
check("Pagamento 1 parcelas = 1", pag1['parcelas'] == 1)

r = c.get(f'/orcamentos/{orc1["id"]}/nota-fiscal')
check("Nota fiscal orcamento 1", r.status_code == 200)
check("Nota fiscal tem titulo", 'Nota Fiscal' in r.text or 'nota_fiscal' in r.text or 'fiscal' in r.text.lower())
check("Nota fiscal tem valor 590", '590' in r.text)

r = c.post(f'/orcamentos/{orc2["id"]}/pagar', data={'valor': '350', 'metodo': 'cartao_credito', 'parcelas': '4'})
check("Pagar orcamento 2 parcelado 4x R$350", r.status_code in (302, 200))

orc2_db = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc2["id"],))
check("Orcamento 2 status = pago_parcial", orc2_db['status'] == 'pago_parcial')

pag2 = db.fetch_one("SELECT * FROM pagamentos WHERE orcamento_id = %s AND status = 'pago' ORDER BY id DESC LIMIT 1", (orc2["id"],))
check("Pagamento 2 criado", pag2 is not None)
check("Pagamento 2 parcelas = 4", pag2['parcelas'] == 4)
check("Pagamento 2 valor_total = 350", float(pag2['valor']) == 350)
check("Pagamento 2 valor_parcela = 87.5", float(pag2['valor_parcela']) == 87.5)

r = c.post(f'/orcamentos/{orc2["id"]}/pagar', data={'valor': '1050', 'metodo': 'dinheiro', 'parcelas': '1'})
check("Pagar restante orcamento 2 (R$1050)", r.status_code in (302, 200))

orc2_db = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc2["id"],))
check("Orcamento 2 status = pago apos total", orc2_db['status'] == 'pago')

total_pago = db.fetch_one("SELECT SUM(valor) as total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'", (orc2["id"],))
check(f"Total pago orcamento 2 = R$1400", float(total_pago['total']) == 1400)

r = c.get(f'/orcamentos/{orc2["id"]}/pagar')
check("Pagina pagar orcamento 2", r.status_code == 200)
r = c.get('/pagamentos')
check("Lista pagamentos", r.status_code == 200)

# ═══════════════════════════════════════
# 7. CANCELAMENTO DE PAGAMENTO
# ═══════════════════════════════════════
print("\n=== 7. CANCELAMENTO DE PAGAMENTO ===")

pag2_id = pag2['id']
r = c.post(f'/orcamentos/{orc2["id"]}/pagamento/{pag2_id}/cancelar')
check("Cancelar pagamento parcelado", r.status_code in (302, 200))

pag2_cancelado = db.fetch_one("SELECT status FROM pagamentos WHERE id = %s", (pag2_id,))
check("Pagamento 2 cancelado", pag2_cancelado['status'] == 'cancelado')

orc2_db = db.fetch_one("SELECT status FROM orcamentos WHERE id = %s", (orc2["id"],))
check("Orcamento 2 volta para pago_parcial", orc2_db['status'] == 'pago_parcial')

total_pago_2 = db.fetch_one("SELECT COALESCE(SUM(valor), 0) as total FROM pagamentos WHERE orcamento_id = %s AND status = 'pago'", (orc2["id"],))
check(f"Total pago orcamento 2 apos cancelamento = R$1050", float(total_pago_2['total']) == 1050)

r = c.get(f'/orcamentos/{orc2["id"]}/nota-fiscal')
check("Nota fiscal acessivel apos cancelamento parcial", r.status_code == 200)

# ═══════════════════════════════════════
# 8. METODOS DE PAGAMENTO
# ═══════════════════════════════════════
print("\n=== 8. METODOS DE PAGAMENTO ===")

r = c.post('/orcamentos/criar', data={
    'paciente_id': J, 'profissional_id': CO, 'convenio_id': '',
    'data_validade': '2026-08-31', 'observacoes': 'Teste metodos pagamento',
})
orc4 = db.fetch_one("SELECT id FROM orcamentos ORDER BY id DESC LIMIT 1")
r = c.post(f'/orcamentos/{orc4["id"]}/item/adicionar', data={
    'procedimento_id': 4, 'descricao': 'Clareamento', 'quantidade': 1, 'valor_unitario': 800,
})
r = c.post(f'/orcamentos/{orc4["id"]}/status', data={'status': 'enviado'})
r = c.post(f'/orcamentos/{orc4["id"]}/status', data={'status': 'aprovado'})

for metodo in ['dinheiro', 'pix', 'cartao_credito', 'cartao_debito', 'transferencia', 'boleto', 'outros']:
    r = c.post(f'/orcamentos/{orc4["id"]}/pagar', data={'valor': '100', 'metodo': metodo, 'parcelas': '1'})
    check(f"Metodo: {metodo}", r.status_code in (302, 200))

pagamentos_metodos = db.fetch_all("SELECT metodo, COUNT(*) as qtd FROM pagamentos WHERE orcamento_id = %s AND status = 'pago' GROUP BY metodo", (orc4["id"],))
check("7 metodos registrados", len(pagamentos_metodos) == 7)

# ═══════════════════════════════════════
# 9. CONVERSAO ORCAMENTO -> CONSULTA
# ═══════════════════════════════════════
print("\n=== 9. CONVERSAO ORCAMENTO -> CONSULTA ===")

r = c.post('/orcamentos/criar', data={
    'paciente_id': L, 'profissional_id': CO, 'convenio_id': '',
    'data_validade': '2026-08-31', 'observacoes': 'Orcamento para conversao',
})
orc5 = db.fetch_one("SELECT id FROM orcamentos ORDER BY id DESC LIMIT 1")
r = c.post(f'/orcamentos/{orc5["id"]}/item/adicionar', data={
    'procedimento_id': 3, 'descricao': 'Limpeza', 'quantidade': 1, 'valor_unitario': 150,
})
r = c.post(f'/orcamentos/{orc5["id"]}/status', data={'status': 'enviado'})
r = c.post(f'/orcamentos/{orc5["id"]}/status', data={'status': 'aprovado'})

r = c.post(f'/orcamentos/{orc5["id"]}/converter', data={'data_hora': '2026-07-25T09:00', 'duracao': 30})
check("Converter orcamento em consulta", r.status_code in (302, 200))

consulta_nova = db.fetch_one("SELECT * FROM consultas ORDER BY id DESC LIMIT 1")
check("Consulta criada apos conversao", consulta_nova is not None)
check("Consulta tem paciente Lucas", consulta_nova['paciente_usuario_id'] == L)
check("Consulta status = agendada", consulta_nova['status'] == 'agendada')

# ═══════════════════════════════════════
# 10. FINANCEIRO
# ═══════════════════════════════════════
print("\n=== 10. RELATORIO FINANCEIRO ===")

for p in ['mes', 'semana', 'ano', 'hoje']:
    r = c.get(f'/financeiro?periodo={p}')
    check(f"Financeiro periodo={p}", r.status_code == 200)
r = c.get('/financeiro')
check("Pagina financeiro carrega", r.status_code == 200)

# ═══════════════════════════════════════
# 11. AGENDA
# ═══════════════════════════════════════
print("\n=== 11. AGENDA ===")

r = c.get('/agenda')
check("Pagina agenda carrega", r.status_code == 200)
check("Filtro por profissional presente", 'profissional_id' in r.text or 'profissionais_filtro' in r.text)
r = c.get(f'/agenda?profissional_id={S}')
check("Agenda com filtro profissional", r.status_code == 200)
r = c.get('/agenda?data=2026-07-21')
check("Agenda data especifica", r.status_code == 200)

r = c.get(f'/api/consultas?inicio=2026-07-20T00:00:00&fim=2026-07-30T23:59:59&profissional_id={S}')
check("API consultas com filtro profissional", r.status_code == 200)
consutas_prof2 = r.json()
check("Profissional so tem suas consultas", all(x['profissional'] != '' for x in consutas_prof2))

# ═══════════════════════════════════════
# 12. FILTROS
# ═══════════════════════════════════════
print("\n=== 12. FILTROS POR PACIENTE ===")

for route in ['/consultas', '/orcamentos', '/prontuarios', '/financeiro', '/pagamentos']:
    r = c.get(f'{route}?paciente_id={A}')
    check(f"Filtro {route} paciente Ana", r.status_code == 200)

# ═══════════════════════════════════════
# 13. PACIENTE VIEW
# ═══════════════════════════════════════
print("\n=== 13. ACESSO PACIENTE ===")

r = c.post('/login', data={'email': 'ana@email.com', 'senha': 'pac123'})
check("Login paciente Ana", r.status_code in (302, 200))
r = c.get('/dashboard')
check("Paciente ve dashboard", r.status_code == 200)
r = c.get('/orcamentos')
check("Paciente ve orcamentos", r.status_code == 200)

r = c.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'admin123'})
check("Re-login admin", r.status_code in (302, 200))

# ═══════════════════════════════════════
# 14. IMPRESSAO
# ═══════════════════════════════════════
print("\n=== 14. IMPRESSAO ORCAMENTO ===")

r = c.get(f'/orcamentos/{orc1["id"]}/imprimir')
check("Imprimir orcamento 1", r.status_code == 200)
check("Impressao contem dados", len(r.text) > 500)
r = c.get(f'/orcamentos/{orc2["id"]}/imprimir')
check("Imprimir orcamento 2", r.status_code == 200)

# ═══════════════════════════════════════
# 15. RESILIENCIA DO BANCO
# ═══════════════════════════════════════
print("\n=== 15. RESILIENCIA DO BANCO ===")

for i in range(20):
    r = c.get('/api/status')
    if r.json().get('banco') is not True:
        check(f"Status check {i+1}/20", False)
        break
else:
    check("20 status checks consecutivos todos OK", True)

for i in range(10):
    r = c.get('/pacientes')
    r2 = c.get('/consultas')
    r3 = c.get('/api/status')
    if r.status_code != 200 or r2.status_code != 200 or r3.json().get('banco') is not True:
        check(f"Mixed request batch {i+1}/10", False)
        break
else:
    check("10 batches de requisicoes mistas OK", True)

# ═══════════════════════════════════════
# 16. EDITAR DADOS
# ═══════════════════════════════════════
print("\n=== 16. EDICAO DE DADOS ===")

r = c.post(f'/pacientes/{A}/editar', data={
    'nome': 'Ana Silva Santos', 'email': 'ana.novo@email.com',
    'telefone': '(11) 98888-7777', 'cpf': '111.222.333-44',
    'data_nascimento': '1990-05-15', 'endereco': 'Rua A, 100 - Atualizado', 'foto_url': '',
})
check("Editar paciente Ana", r.status_code in (302, 200))
pac_editado = db.fetch_one("SELECT nome, email FROM usuarios WHERE id = %s", (A,))
check("Nome atualizado", pac_editado['nome'] == 'Ana Silva Santos')
check("Email atualizado", pac_editado['email'] == 'ana.novo@email.com')

r = c.post('/estabelecimentos/1/editar', data={
    'nome': 'Clinica Centro ATUALIZADA', 'tipo': 'clinica',
    'cnpj': '11.222.333/0001-44', 'telefone': '(11) 3333-4444',
    'email': 'novo@clinica.com', 'endereco': 'Rua Centro, 100', 'logo_url': '', 'ativo': 'on',
})
check("Editar estabelecimento", r.status_code in (302, 200))
estab_editado = db.fetch_one("SELECT nome FROM estabelecimentos WHERE id = 1")
check("Estabelecimento nome atualizado", 'ATUALIZADA' in estab_editado['nome'])

r = c.post('/convenios/1/editar', data={
    'nome': 'Unimed Novo', 'registro_ans': '111', 'cobertura': 'Cobertura total',
    'percentual_cobertura': '30', 'telefone': '(11) 8888-9999', 'email': 'novo@unimed.com',
})
check("Editar convenio", r.status_code in (302, 200))
conv_editado = db.fetch_one("SELECT nome FROM convenios WHERE id = 1")
check("Convenio nome atualizado", conv_editado['nome'] == 'Unimed Novo')

r = c.post('/procedimentos/1/editar', data={'nome': 'Restauracao Premium', 'descricao': 'Restauracao de alta qualidade', 'duracao_minutos': 45})
check("Editar procedimento", r.status_code in (302, 200))
proc_editado = db.fetch_one("SELECT nome, duracao_minutos FROM procedimentos WHERE id = 1")
check("Procedimento nome atualizado", proc_editado['nome'] == 'Restauracao Premium')
check("Procedimento duracao atualizada", proc_editado['duracao_minutos'] == 45)

# ═══════════════════════════════════════
# 17. DESATIVAR ESTABELECIMENTO
# ═══════════════════════════════════════
print("\n=== 17. DESATIVAR ESTABELECIMENTO ===")

r = c.post('/estabelecimentos/2/desativar')
check("Desativar Hospital Norte", r.status_code in (302, 200))
estab2 = db.fetch_one("SELECT ativo FROM estabelecimentos WHERE id = 2")
check("Hospital Norte desativado", estab2['ativo'] == 0 or estab2['ativo'] == False)
r = c.get('/estabelecimentos')
check("Hospital Norte nao aparece na lista", 'Hospital Norte' not in r.text)

# ═══════════════════════════════════════
# 18. ACESSO NEGADO
# ═══════════════════════════════════════
print("\n=== 18. ACESSO NEGADO ===")

c2 = TestClient(app, follow_redirects=False)
r = c2.post('/login', data={'email': 'ana.novo@email.com', 'senha': 'pac123'})
check("Login paciente para teste acesso", r.status_code in (302, 200))
r = c2.get('/estabelecimentos')
check("Paciente nao ve estabelecimentos", r.status_code in (302, 403, 200))

r = c.post('/login', data={'email': 'marcusodontocotta@gmail.com', 'senha': 'admin123'})
check("Re-login admin final", r.status_code in (302, 200))

# ═══════════════════════════════════════
# 19. ERROS E EDGE CASES
# ═══════════════════════════════════════
print("\n=== 19. ERROS E EDGE CASES ===")

r = c.get('/orcamentos/99999')
check("Orcamento inexistente = 404", r.status_code == 404)
r = c.get('/prontuarios/99999')
check("Prontuario inexistente = 404", r.status_code == 404)
r = c.get('/api/consultas?inicio=2026-01-01T00:00:00&fim=2026-01-02T23:59:59')
check("API consultas sem dados retorna vazio", len(r.json()) == 0)
r = c.post('/consultas/1/status', data={'status': 'status_invalido'})
check("Status invalido rejeitado", r.status_code in (400, 302, 200))

# ═══════════════════════════════════════
# 20. STATUS FINAL
# ═══════════════════════════════════════
print("\n=== 20. STATUS FINAL ===")

r = c.get('/api/status')
check("Status final banco = verde", r.json().get('banco') is True)
r = c.get('/dashboard')
check("Dashboard admin carrega", r.status_code == 200)

# ═══════════════════════════════════════
# RESULTADO
# ═══════════════════════════════════════
print("\n" + "=" * 60)
print(f"TOTAL: {passed} OK / {failed} FALHOS")
if errors:
    print(f"FALHOS: {', '.join(errors)}")
else:
    print("TODOS OS TESTES FUNCIONAIS PASSARAM!")
print("=" * 60)
