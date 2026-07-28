import os
import sys
import pymysql
import bcrypt
from datetime import datetime, timedelta
import random
from urllib.parse import urlparse

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: Set DATABASE_URL environment variable"); sys.exit(1)

parsed = urlparse(DB_URL)
conn = pymysql.connect(host=parsed.hostname, user=parsed.username, password=parsed.password, database=parsed.path.lstrip("/"), charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()

def hash_senha(s):
    return bcrypt.hashpw(s.encode(), bcrypt.gensalt()).decode()

def uid(nome, email, tipo, tel=None, cpf=None, dn=None, end=None):
    cur.execute("INSERT INTO usuarios (nome,email,senha_hash,tipo,telefone,cpf,data_nascimento,endereco) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (nome, email, hash_senha('123456'), tipo, tel, cpf, dn, end))
    conn.commit()
    return cur.lastrowid

print("=== LIMPA ===")
for t in ['pagamentos','orcamento_itens','orcamentos','tratamentos','evolucoes','consultas','prontuarios','paciente_convenio','paciente_estabelecimento','profissional_estabelecimento','usuarios','estabelecimentos','procedimentos','convenios']:
    try: cur.execute(f"DELETE FROM {t}"); conn.commit()
    except: conn.rollback()
    try: cur.execute(f"ALTER TABLE {t} AUTO_INCREMENT = 1"); conn.commit()
    except: conn.rollback()

# Procedimentos
print("=== PROCEDIMENTOS ===")
procs = []
for n, d, dur in [('Restauracao','Restauracao dentaria',45),('Extracao','Extracao dentaria',60),('Limpeza','Limpeza e profilaxia',30),('Clareamento','Clareamento dental',90),('Implante','Implante dentario',120),('Canal','Tratamento endodontico',60),('Protese','Protese dentaria',45),('Avaliacao','Avaliacao clinica geral',30),('Raio-X','Radiografia panoramica',15),('Manutencao','Manutencao de aparelho',30)]:
    cur.execute("INSERT INTO procedimentos (nome,descricao,duracao_minutos) VALUES (%s,%s,%s)",(n,d,dur)); conn.commit()
    procs.append(cur.lastrowid)

# Convenios
print("=== CONVENIOS ===")
convs = []
for n, cnpj, tel in [('Unimed','11.222.333/0001-44','0800-111-2222'),('Bradesco Saude','22.333.444/0001-55','0800-333-4444'),('Amil','33.444.555/0001-66','0800-555-6666'),('SulAmerica','44.555.666/0001-77','0800-777-8888'),('Particular',None,None)]:
    cur.execute("INSERT INTO convenios (nome,cnpj,telefone) VALUES (%s,%s,%s)",(n,cnpj,tel)); conn.commit()
    convs.append(cur.lastrowid)

# Admin
print("=== ADMIN ===")
admin_id = uid('Administrador','marcusodontocotta@gmail.com','admin','11999990000','000.000.000-00','1980-01-01','Rua Admin, 100')
cur.execute("UPDATE usuarios SET senha_hash=%s, is_super=TRUE WHERE id=%s",(hash_senha('admin123'),admin_id)); conn.commit()
cur.execute("INSERT INTO estabelecimentos (nome,tipo,ativo) VALUES (%s,'clinica',1)",('SISGERSA Clinica Principal',)); conn.commit()
estab_id = cur.lastrowid
cur.execute("INSERT INTO profissional_estabelecimento (usuario_id,estabelecimento_id) VALUES (%s,%s)",(admin_id,estab_id)); conn.commit()

# Profissionais
print("=== PROFISSIONAIS ===")
profs = []
for i,(n,esp,crg,reg) in enumerate([('Dr. Carlos Silva','Odontologia Geral','Dentista','CRO-12345'),('Dra. Ana Souza','Ortodontia','Dentista','CRO-23456'),('Dr. Paulo Mendes','Endodontia','Dentista','CRO-34567'),('Dra. Julia Ferreira','Periodontia','Dentista','CRO-45678'),('Dr. Ricardo Santos','Protese','Dentista','CRO-56789')],1):
    pid = uid(n,f'prof{i}@sisgersa.com','profissional',f'1198888{i:04d}',f'111.222.333-{44+i:02d}',f'198{i}-03-15',f'Rua Medico {i}, {i*100}')
    cur.execute("INSERT INTO profissional_estabelecimento (usuario_id,estabelecimento_id,especialidade,cargo,registro_profissional) VALUES (%s,%s,%s,%s,%s)",(pid,estab_id,esp,crg,reg)); conn.commit()
    profs.append(pid)

# Pacientes
print("=== PACIENTES ===")
pacientes = []
pdata = [
    ('Maria Oliveira','maria@email.com','11977770001','123.456.789-00','1990-05-10','Rua das Flores, 101'),
    ('Pedro Santos','pedro@email.com','11977770002','234.567.890-11','1985-08-22','Av. Brasil, 202'),
    ('Lucia Ferreira','lucia@email.com','11977770003','345.678.901-22','1978-12-01','Rua da Paz, 303'),
    ('Roberto Costa','roberto@email.com','11977770004','456.789.012-33','1992-03-18','Rua do Sol, 404'),
    ('Ana Lima','ana.lima@email.com','11977770005','567.890.123-44','1988-07-25','Av. Paulista, 505'),
    ('Fernanda Ribeiro','fernanda@email.com','11977770006','678.901.234-55','1995-11-30','Rua da Lua, 606'),
    ('Marcos Almeida','marcos@email.com','11977770007','789.012.345-66','1982-04-14','Rua das Estrelas, 707'),
    ('Juliana Pereira','juliana@email.com','11977770008','890.123.456-77','1991-09-08','Av. Reboucas, 808'),
    ('Lucas Martins','lucas@email.com','11977770009','901.234.567-88','1987-01-20','Rua Augusta, 909'),
    ('Camila Rodrigues','camila@email.com','11977770010','012.345.678-99','1993-06-12','Rua Oscar Freire, 1010'),
    ('Thiago Araujo','thiago@email.com','11977770011','111.222.333-01','1980-10-05','Rua Haddock Lobo, 1111'),
    ('Patricia Gomes','patricia@email.com','11977770012','222.333.444-02','1994-02-28','Rua Bela Cintra, 1212'),
    ('Rafael Dias','rafael@email.com','11977770013','333.444.555-03','1986-08-17','Av. Faria Lima, 1313'),
    ('Bianca Moreira','bianca@email.com','11977770014','444.555.666-04','1997-04-03','Rua dos Pinheiros, 1414'),
    ('Gustavo Barbosa','gustavo@email.com','11977770015','555.666.777-05','1983-11-22','Rua Cardeal Arcoverde, 1515'),
    ('Isabela Nascimento','isabela@email.com','11977770016','666.777.888-06','1990-07-09','Rua Purpura, 1616'),
    ('Diego Carvalho','diego@email.com','11977770017','777.888.999-07','1989-05-16','Rua Artur de Azevedo, 1717'),
    ('Vanessa Lopes','vanessa@email.com','11977770018','888.999.000-08','1996-12-24','Rua Mourato Coelho, 1818'),
    ('Leonardo Rocha','leonardo@email.com','11977770019','999.000.111-09','1984-03-07','Rua Girassol, 1919'),
    ('Amanda Castro','amanda@email.com','11977770020','000.111.222-10','1998-09-14','Rua Harmonia, 2020'),
    ('Felipe Vieira','felipe@email.com','11977770021','121.343.565-78','1981-06-21','Rua Fidalga, 2121'),
    ('Priscila Mendonca','priscila@email.com','11977770022','232.454.676-89','1993-01-30','Rua Wisard, 2222'),
    ('Andre Teixeira','andre@email.com','11977770023','343.565.787-90','1987-10-11','Rua Capote Valente, 2323'),
    ('Daniela Campos','daniela@email.com','11977770024','454.676.898-01','1995-08-02','Rua dos Chanes, 2424'),
]
for nome,email,tel,cpf,dn,end in pdata:
    pid = uid(nome,email,'paciente',tel,cpf,dn,end)
    cur.execute("INSERT INTO paciente_estabelecimento (usuario_id,estabelecimento_id) VALUES (%s,%s)",(pid,estab_id)); conn.commit()
    for ci in random.sample(range(4), random.randint(1,2)):
        cur.execute("INSERT INTO paciente_convenio (paciente_usuario_id,convenio_id,numero_carteirinha,validade) VALUES (%s,%s,%s,%s)",
                    (pid,convs[ci],f"{convs[ci]:04d}{pid:06d}",'2027-12-31')); conn.commit()
    pacientes.append(pid)
print(f"  {len(pacientes)} pacientes")

# Prontuarios
print("=== PRONTUARIOS ===")
pront_ids = []
for i,pac_id in enumerate(pacientes,1):
    cur.execute("INSERT INTO prontuarios (paciente_usuario_id,estabelecimento_id,numero_prontuario) VALUES (%s,%s,%s)",(pac_id,estab_id,f"PRONT-{i:04d}")); conn.commit()
    pront_ids.append(cur.lastrowid)
print(f"  {len(pront_ids)} prontuarios")

# Consultas
print("=== CONSULTAS ===")
statuses = ['concluida','concluida','concluida','agendada','confirmada','em_andamento','cancelada','faltou']
for pac_id in pacientes:
    for j in range(random.randint(2,6)):
        dias = random.randint(0,90)
        hora = random.choice([8,9,10,11,14,15,16,17])
        dh = (datetime.now()-timedelta(days=dias)).replace(hour=hora,minute=0,second=0,microsecond=0)
        st = random.choice(statuses)
        dur = random.choice([30,45,60])
        pront = random.choice(pront_ids) if random.random()>0.3 else None
        proc = random.choice(procs) if random.random()>0.4 else None
        cur.execute("INSERT INTO consultas (paciente_usuario_id,profissional_usuario_id,estabelecimento_id,data_hora,duracao_minutos,status,prontuario_id,procedimento_id,observacoes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (pac_id,random.choice(profs),estab_id,dh,dur,st,pront,proc,random.choice(['Rotina','Dor intensa','Retorno','Avaliacao inicial',None]))); conn.commit()

# Evolucoes (ligadas a prontuarios)
print("=== EVOLUCOES ===")
evo_count = 0
for pront_id in pront_ids:
    if random.random()>0.3:
        cur.execute("INSERT INTO evolucoes (prontuario_id,profissional_usuario_id,queixa_principal,diagnostico,procedimento_realizado,observacoes) VALUES (%s,%s,%s,%s,%s,%s)",
                    (pront_id,random.choice(profs),
                     random.choice(['Dor de dente','Gengiva sangrando','Dente quebrado','Manchas nos dentes','Dor de mandibula']),
                     random.choice(['Carie','Gengivite','Fratura','Maloclusao','Desgaste']),
                     random.choice(['Restauracao','Extracao','Limpeza','Clareamento','Canal']),
                     random.choice(['Paciente orientado sobre higiene','Retorno em 30 dias','Sem intercorrencias',None]))); conn.commit()
        evo_count += 1
print(f"  {evo_count} evolucoes")

# Orcamentos e Pagamentos
print("=== ORCAMENTOS E PAGAMENTOS ===")
metodos = ['dinheiro','pix','cartao_credito','cartao_debito','transferencia','boleto']
orc_total = 0
pag_total = 0

for pac_id in pacientes:
    for k in range(random.randint(4,7)):
        conv_id = random.choice(convs[:4]) if random.random()>0.2 else None
        status_orc = random.choice(['rascunho','enviado','aprovado','aprovado','pago','pago','pago_parcial','rejeitado','expirado'])
        dc = datetime.now()-timedelta(days=random.randint(1,60))
        vd = dc+timedelta(days=30)

        cur.execute("INSERT INTO orcamentos (paciente_usuario_id,profissional_usuario_id,estabelecimento_id,convenio_id,status,data_validade,observacoes,criado_em) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (pac_id,random.choice(profs),estab_id,conv_id,status_orc,vd,random.choice(['Tratamento completo','Procedimento estetico','Emergencia',None]),dc)); conn.commit()
        orc_id = cur.lastrowid
        orc_total += 1

        n_itens = random.randint(2,5)
        vtotal = 0
        for proc_id in random.sample(procs, min(n_itens,len(procs))):
            v = random.choice([150,200,250,300,350,400,500,600,800,1000,1200])
            cur.execute("INSERT INTO orcamento_itens (orcamento_id,procedimento_id,descricao,quantidade,valor_unitario,subtotal) VALUES (%s,%s,%s,1,%s,%s)",
                        (orc_id,proc_id,f'Procedimento',v,v)); conn.commit()
            vtotal += v
        cur.execute("UPDATE orcamentos SET valor_total=%s WHERE id=%s",(vtotal,orc_id)); conn.commit()

        if status_orc == 'pago':
            metodo = random.choice(metodos)
            parc = random.choice([1,1,1,2,3])
            vp = round(vtotal/parc,2)
            cur.execute("INSERT INTO pagamentos (orcamento_id,valor,metodo,parcelas,valor_parcela,data_pagamento,status) VALUES (%s,%s,%s,%s,%s,%s,'pago')",
                        (orc_id,vtotal,metodo,parc,vp,(dc+timedelta(days=random.randint(0,15))).strftime('%Y-%m-%d'))); conn.commit()
            pag_total += 1
        elif status_orc == 'pago_parcial':
            pct = random.uniform(0.4,0.8)
            pago = round(vtotal*pct,2)
            metodo = random.choice(metodos)
            parc = random.choice([1,2,3])
            vp = round(pago/parc,2)
            cur.execute("INSERT INTO pagamentos (orcamento_id,valor,metodo,parcelas,valor_parcela,data_pagamento,status) VALUES (%s,%s,%s,%s,%s,%s,'pago')",
                        (orc_id,pago,metodo,parc,vp,(dc+timedelta(days=random.randint(0,10))).strftime('%Y-%m-%d'))); conn.commit()
            pag_total += 1
            restante = round(vtotal-pago,2)
            if restante > 0:
                cur.execute("INSERT INTO pagamentos (orcamento_id,valor,metodo,parcelas,valor_parcela,data_pagamento,status) VALUES (%s,%s,%s,1,%s,%s,'pago')",
                            (orc_id,restante,random.choice(metodos),restante,(dc+timedelta(days=random.randint(10,25))).strftime('%Y-%m-%d'))); conn.commit()
                pag_total += 1

print(f"  {orc_total} orcamentos, {pag_total} pagamentos")

# Resumo
print("\n=== RESUMO ===")
cur.execute("SELECT tipo,COUNT(*) as qtd FROM usuarios GROUP BY tipo")
for r in cur.fetchall(): print(f"  {r['tipo']}: {r['qtd']}")
for t in ['consultas','orcamentos','pagamentos','evolucoes','prontuarios','procedimentos','convenios']:
    cur.execute(f"SELECT COUNT(*) as qtd FROM {t}"); print(f"  {t}: {cur.fetchone()['qtd']}")

print("\n=== SEED COMPLETO ===")
print("Admin: admin@sisgersa.com / admin123")
print("Pacientes: [nome]@email.com / 123456")
cur.close(); conn.close()
