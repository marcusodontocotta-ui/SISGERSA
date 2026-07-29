import psycopg, openpyxl, time
from collections import defaultdict

DB = dict(
    host='dpg-d9hqikr7uimc73dt3e0g-a.oregon-postgres.render.com',
    port=5432, user='sisgersa',
    password='tOJ0rv1qWUQABYIWRMO0ew2c2AtfGZNU',
    dbname='sisgersa',
)

conn = psycopg.connect(**DB, connect_timeout=30, autocommit=True)
cur = conn.cursor()

# Mappings
cur.execute("SELECT id, codigo_paciente FROM pacientes WHERE codigo_paciente IS NOT NULL")
pac_map = {}
for pid, cod in cur.fetchall():
    try: pac_map[int(cod)] = pid
    except: pass

cur.execute("SELECT old_codigo, new_id FROM _old_prof_map")
prof_map = {int(r[0]): r[1] for r in cur.fetchall()}
prof_map[0] = 8294

wb_proc = openpyxl.load_workbook(r'C:\Users\T-GAMER\Documents\Default Project\medical_db\T_procedimento.xlsx', read_only=True)
ws_proc = wb_proc.active
old_procs = {}
for r in ws_proc.iter_rows(min_row=2, values_only=True):
    if r[0] is not None: old_procs[int(r[0])] = {'nome': str(r[1] or ''), 'preco': float(r[2] or 0)}

cur.execute("SELECT id, nome FROM procedimentos")
new_procs = {r[0]: r[1] for r in cur.fetchall()}
old_to_new_proc = {}
for oc, od in old_procs.items():
    on = od['nome'].strip().lower()
    if oc in new_procs: old_to_new_proc[oc] = oc; continue
    for nid, nn in new_procs.items():
        if on == nn.strip().lower(): old_to_new_proc[oc] = nid; break

cur.execute("SELECT estabelecimento_id FROM paciente_estabelecimento GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1")
default_estab = cur.fetchone()[0]
print(f"Pac:{len(pac_map)} Prof:{len(prof_map)} Proc:{len(old_to_new_proc)} Estab:{default_estab}")

# Sub items
print("Sub...")
wb_sub = openpyxl.load_workbook(r'C:\Users\T-GAMER\Documents\Default Project\medical_db\T_sub orçamento.xlsx', read_only=True)
ws_sub = wb_sub.active
sub_items = defaultdict(list)
for r in ws_sub.iter_rows(min_row=2, values_only=True):
    if r[0] is not None: sub_items[int(r[0])].append(r)
print(f"  {len(sub_items)} orcs com itens")

# Pre-process items into (orc_id, values_list)
print("Processando itens...")
item_data = {}  # old_orc_id -> list of item tuples
for old_orc_id, items in sub_items.items():
    processed = []
    for item in items:
        try:
            old_proc = int(item[2]) if item[2] is not None else None
            preco = float(item[3] or 0); di = float(item[5] or 0)
            subtt = float(item[10] or 0)
            if subtt == 0 and preco > 0: subtt = preco - di
            dente = str(item[4] or '').strip()
            qtd = int(item[8] or 1) if item[8] else 1
            npid = old_to_new_proc.get(old_proc) if old_proc else None
            nome_proc = old_procs.get(old_proc, {}).get('nome', '') if old_proc else ''
            desc = nome_proc
            if dente: desc = f"{desc} (dente {dente})" if desc else f"Procedimento dente {dente}"
            processed.append((npid, desc, qtd, preco, di, subtt))
        except:
            pass
    if processed:
        item_data[old_orc_id] = processed
print(f"  {len(item_data)} orcs com itens processados")

# Orcamentos
print("Orcamentos...")
wb = openpyxl.load_workbook(r'C:\Users\T-GAMER\Documents\Default Project\medical_db\T_orçamento.xlsx', read_only=True)
ws = wb.active

def status(c,p,cl):
    c=(c or '').strip().upper();p=(p or '').strip().upper();cl=(cl or '').strip().upper()
    if p in ('SIM','S'): return 'pago'
    if cl in ('SIM','S'): return 'aprovado'
    if c in ('SIM','S'): return 'aprovado'
    if c in ('NÃO','NAO','NO','N'): return 'rejeitado'
    return 'enviado'

# Check how many already imported
cur2 = conn.cursor()
cur2.execute("SELECT COUNT(*) FROM orcamentos")
ja_importados = cur2.fetchone()[0]
cur2.close()
print(f"Ja importados anteriormente: {ja_importados}")

conn.autocommit = False

oi, ii, sk, er = 0, 0, 0, 0
batch_orc_sql = []
batch_orc_params = []
batch_item_sqls = []
batch_num = 0

def flush_batch():
    global batch_orc_sql, batch_orc_params, batch_item_sqls, batch_num, conn, cur
    if not batch_orc_sql:
        return True
    try:
        for i, (orc_sql, orc_params, item_tuples) in enumerate(zip(batch_orc_sql, batch_orc_params, batch_item_sqls)):
            r = cur.execute(orc_sql, orc_params)
            nid = r.fetchone()[0]
            for it in item_tuples:
                cur.execute("INSERT INTO orcamento_itens (orcamento_id,procedimento_id,descricao,quantidade,valor_unitario,desconto,subtotal,criado_em) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())", (nid,) + it)
        conn.commit()
        return True
    except Exception as e:
        try: conn.rollback()
        except: pass
        return False

for row in ws.iter_rows(min_row=2, values_only=True):
    try:
        old_id, dt, op, opr, obs, cf, pg, cl = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
        vt = float(row[12] or 0)
    except:
        er += 1; continue
    if old_id is None or op is None:
        sk += 1; continue
    np = pac_map.get(int(op))
    if np is None:
        sk += 1; continue
    npr = prof_map.get(int(opr) if opr is not None else 0, 8294)
    sts = status(cf, pg, cl)
    
    batch_orc_sql.append("INSERT INTO orcamentos (paciente_usuario_id,profissional_usuario_id,estabelecimento_id,status,observacoes,valor_total,criado_em,atualizado_em) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id")
    batch_orc_params.append((np, npr, default_estab, sts, str(obs or ''), vt, dt, dt))
    batch_item_sqls.append(item_data.get(int(old_id), []))
    oi += 1
    batch_num += 1
    
    if batch_num >= 30:
        ok = flush_batch()
        if ok:
            ii += sum(len(items) for items in batch_item_sqls)
            print(f"  {oi} orcs, {ii} itens...")
        else:
            er += batch_num
            print(f"  ERRO no batch, reconectando e tentando novamente...")
            conn = psycopg.connect(**DB, connect_timeout=30, autocommit=True)
            cur = conn.cursor()
            conn.autocommit = False
        batch_orc_sql, batch_orc_params, batch_item_sqls = [], [], []
        batch_num = 0

# Last batch
ok = flush_batch()
ii += sum(len(items) for items in batch_item_sqls)
if ok:
    print(f"  {oi} orcs, {ii} itens...")
else:
    er += batch_num
    print(f"  ERRO no ultimo batch")

print(f"\nOK: O={oi} I={ii} Skip={sk} Err={er}")
conn.close()
