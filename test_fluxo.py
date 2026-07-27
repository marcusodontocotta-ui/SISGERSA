import sys
sys.path.insert(0, '.')
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

print("=== 1. Login ===")
r = client.post("/login", data={"email": "guiaparaoinesperado@gmail.com", "senha": "Ong6132"}, follow_redirects=False)
print(f"Status: {r.status_code}")
if r.status_code in (301, 302):
    print(f"Redirect: {r.headers.get('location')}")
    print(f"Token: {'token' in dict(r.cookies)}")
    estab = r.cookies.get('estabelecimento_id', 'NAO SETADO')
    print(f"Estab cookie: {estab}")
else:
    print(f"Erro - body: {r.text[:300]}")
    sys.exit(1)

print("\n=== 2. Dashboard ===")
r2 = client.get("/dashboard", follow_redirects=False)
print(f"Status: {r2.status_code}")
if r2.status_code in (301, 302):
    print(f"Redirect: {r2.headers.get('location')}")
elif r2.status_code == 200:
    if "Painel Administrativo Geral" in r2.text:
        print("Template: admin.html (super admin) - ERRO, era pra ser admin_estab")
    elif "admin_estab" in r2.text or "Meu Estabelecimento" in r2.text or "Consultorio" in r2.text.lower():
        print("Template: admin_estab.html - CORRETO!")
    else:
        # Find title
        import re
        title = re.search(r'<h2[^>]*>(.*?)</h2>', r2.text)
        print(f"Titulo: {title.group(1) if title else 'desconhecido'}")

print("\n=== 3. API Estabelecimentos ===")
r3 = client.get("/api/estabelecimentos")
if r3.status_code == 200:
    try:
        data = r3.json()
        estabs = data.get("estabelecimentos", [])
        print(f"Total: {len(estabs)}")
        for e in estabs:
            print(f"  id={e.get('id')} | {e.get('nome')}")
    except:
        print(f"Nao JSON: {r3.text[:200]}")
else:
    print(f"Status: {r3.status_code}")

print("\n=== 4. Selecionar Estab 4 ===")
r4 = client.post("/estabelecimento/selecionar", data={"estabelecimento_id": "4"}, follow_redirects=False)
print(f"Status: {r4.status_code}")
estab_after = client.cookies.get('estabelecimento_id', 'NAO')
print(f"Estab cookie apos: {estab_after}")

print("\n=== 5. Prontuarios ===")
r5 = client.get("/prontuarios", follow_redirects=False)
print(f"Status: {r5.status_code}")
if r5.status_code == 200:
    import re
    rows = re.findall(r'<tr>', r5.text)
    print(f"Linhas <tr>: {len(rows)}")
    if "Nenhum" in r5.text or "nenhum" in r5.text:
        print("Pagina vazia")
    else:
        print("Pagina tem dados!")
elif r5.status_code in (301, 302):
    print(f"Redirect: {r5.headers.get('location')}")

print("\n=== 6. Lista Pacientes ===")
r6 = client.get("/pacientes", follow_redirects=False)
print(f"Status: {r6.status_code}")
if r6.status_code in (301, 302):
    print(f"Redirect: {r6.headers.get('location')}")
elif r6.status_code == 200:
    import re
    rows = re.findall(r'<tr>', r6.text)
    print(f"Linhas <tr>: {len(rows)}")
