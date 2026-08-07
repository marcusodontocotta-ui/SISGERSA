import psycopg, openpyxl, json
from collections import defaultdict
from utils.db_url import get_database_url

EXCEL = r'C:\Users\T-GAMER\Documents\Default Project\medical_db\T_anamnese.xlsx'

conn = psycopg.connect(get_database_url(), connect_timeout=30)
cur = conn.cursor()

print("=== Limpeza de duplicatas ===")
cur.execute("""
    DELETE FROM anamnese a USING (
        SELECT id, paciente_id, ROW_NUMBER() OVER (PARTITION BY paciente_id ORDER BY id) as rn
        FROM anamnese
    ) dup WHERE a.id = dup.id AND dup.rn > 1
""")
print(f"Duplicatas removidas: {cur.rowcount}")

print("\n=== Adicionando UNIQUE constraint ===")
try:
    cur.execute("ALTER TABLE anamnese ADD CONSTRAINT anamnese_paciente_id_unique UNIQUE (paciente_id)")
    print("Constraint UNIQUE adicionada")
except Exception as e:
    if "already exists" in str(e):
        print("Constraint ja existe")
    else:
        print(f"Erro: {e}")

# Map old codes to new paciente IDs
cur.execute("SELECT id, codigo_paciente FROM pacientes WHERE codigo_paciente IS NOT NULL")
code_to_id = {}
for pid, cid in cur.fetchall():
    try:
        code_to_id[int(cid)] = pid
    except:
        pass
print(f"Pacientes mapeados: {len(code_to_id)}")

# Load Excel
print("Carregando Excel...")
wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
ws = wb.active

REV_SIST_NAMES = [
    'Hipertensao','Febre_reumatica','Sopros','Anomalias_congenitas',
    'Hipotensao','Arritmias','Enfarte_miocardio','Asma',
    'Doenca_pulmonar_obstrutiva_cronica','Tuberculose','Hepatite',
    'Gastrite','Ulcera','Infeccao_trato_urinario','Doencas_venereas',
    'Diabete_melito','Disturbio_glandulas_adrenais',
    'Disturbios_tireoide','Gravidez','Apoplexia','Convulsoes',
    'Disturbios_sangramento','Infeccao_recorrente',
]

pacientes_data = defaultdict(list)
for row in ws.iter_rows(min_row=2, values_only=True):
    old_code = row[1]
    if old_code is None:
        continue
    old_code = int(old_code)
    if old_code == 0:
        continue
    pid = code_to_id.get(old_code)
    if pid is None:
        continue
    pacientes_data[pid].append(row)

print(f"Pacientes com dados: {len(pacientes_data)}")

# Check which already exist
cur.execute("SELECT paciente_id FROM anamnese")
existing = set(r[0] for r in cur.fetchall())
print(f"Ja existentes no DB: {len(existing)}")

insert_sql = """
    INSERT INTO anamnese (
        paciente_id, queixa_principal, historico_doenca_atual,
        historico_medico, alergias, medicacoes_em_uso,
        etilismo, observacoes, revisao_sistemas, criado_em
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
    ON CONFLICT (paciente_id) DO NOTHING
"""

count = 0
skipped_existing = 0
skipped_empty = 0
errors = 0

for pid, records in pacientes_data.items():
    if pid in existing:
        skipped_existing += 1
        continue

    merged = [None] * 64
    for rec in records:
        for i, val in enumerate(rec):
            if merged[i] is None and val is not None and str(val).strip():
                merged[i] = val

    queixa = str(merged[3] or '')
    hda = str(merged[4] or '')
    hp = str(merged[5] or '')
    medicamentos = str(merged[34] or '')
    observacoes = str(merged[63] or '')

    alergia_bool = merged[35]
    substancia = str(merged[36] or '')
    if alergia_bool and substancia:
        alergias = substancia
    elif alergia_bool:
        alergias = 'Sim'
    elif substancia:
        alergias = substancia
    else:
        alergias = ''

    etilismo = 'Sim' if merged[29] else ''

    rev_sist = {}
    for idx, name in enumerate(REV_SIST_NAMES):
        val = merged[6 + idx]
        rev_sist[name] = bool(val) if val is not None else False

    if not queixa and not hda and not hp and not medicamentos and not alergias and not observacoes:
        skipped_empty += 1
        continue

    try:
        cur.execute(insert_sql, (
            pid, queixa.strip(), hda.strip(), hp.strip(),
            alergias.strip(), medicamentos.strip(),
            etilismo.strip(), observacoes.strip(), json.dumps(rev_sist)
        ))
        if cur.rowcount > 0:
            count += 1
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"ERRO paciente_id={pid}: {e}")

conn.commit()
cur.close()
conn.close()

print(f"\n=== Concluido ===")
print(f"Inseridos: {count}")
print(f"Ja existiam: {skipped_existing}")
print(f"Pulados (vazios): {skipped_empty}")
print(f"Erros: {errors}")
