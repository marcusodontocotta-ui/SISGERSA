import sys
sys.path.insert(0, '.')
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

print("=== 1. Login ===")
r = client.post("/login", data={"email": "guiaparaoinesperado@gmail.com", "senha": "Ong6132"}, follow_redirects=False)
print(f"Status: {r.status_code}, Redirect: {r.headers.get('location', '-')}")

print("\n=== 2. Dashboard (sem estab) ===")
r2 = client.get("/dashboard", follow_redirects=False)
print(f"Status: {r2.status_code}")
if r2.status_code in (301, 302):
    print(f"Redirect: {r2.headers.get('location')}")
elif r2.status_code == 200:
    if "Selecionar Estabelecimento" in r2.text:
        print(">>> TELA DE SELECAO! (CORRETO)")
        import re
        estabs = re.findall(r'<div class="fw-bold fs-5">(.*?)</div>', r2.text)
        for e in estabs:
            print(f"  -> {e.strip()}")
    elif "Meu Estabelecimento" in r2.text:
        print(">>> Dashboard generico (ERRADO)")
    elif "admin_estab" in r2.text:
        print(">>> Dashboard do estab")

print("\n=== 3. Selecionar Estab 4 ===")
r3 = client.post("/estabelecimento/selecionar", data={"estabelecimento_id": "4"}, follow_redirects=False)
print(f"Status: {r3.status_code}")
estab = client.cookies.get('estabelecimento_id', 'NAO')
print(f"Estab cookie: {estab}")

print("\n=== 4. Dashboard (com estab 4) ===")
r4 = client.get("/dashboard", follow_redirects=False)
print(f"Status: {r4.status_code}")
if r4.status_code == 200:
    import re
    title = re.search(r'<h2[^>]*>(.*?)</h2>', r4.text)
    if title:
        print(f"Titulo: {title.group(1).strip()}")
    if "Consultorio" in r4.text or "Marcus Cotta" in r4.text:
        print(">>> CORRETO: Mostra o consultorio certo!")
    elif "Meu Estabelecimento" in r4.text:
        print(">>> ERRO: Ainda generico")
