import openpyxl

wb = openpyxl.load_workbook('T_cliente.xlsx')
ws = wb['T_cliente']
headers = [str(c.value).strip() if c.value else '' for c in ws[1]]

for i, h in enumerate(headers):
    if 'digo' in h.lower() or 'docum' in h.lower():
        print(f"  [{i}] '{h}' bytes={h.encode('utf-8')}")
